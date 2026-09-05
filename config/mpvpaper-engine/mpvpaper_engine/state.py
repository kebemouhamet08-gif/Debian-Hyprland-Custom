"""Volatile, reconstructible runtime state for MPVpaper Engine."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import tempfile
import threading
from typing import Any

from .models import OutputMode, PerformanceMode, PlaybackState, PlaybackStatus
from .paths import EnginePaths


STATE_VERSION = 1
LOGGER = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _datetime(value: Any, default: datetime | None = None) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return default or utc_now()


def _enum(enum_type, value, default):
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class EngineState:
    version: int = STATE_VERSION
    updated_at: datetime = field(default_factory=utc_now)
    service_status: str = "stopped"
    mode: OutputMode = OutputMode.INDEPENDENT
    outputs: dict[str, PlaybackState] = field(default_factory=dict)
    last_error: str | None = None


def playback_state_to_dict(state: PlaybackState) -> dict[str, Any]:
    path = str(state.path) if state.path is not None else None
    return {
        "status": state.status.value,
        "wallpaper_id": state.wallpaper_id,
        "path": path,
        "title": Path(path).stem if path else None,
        "position": state.position,
        "duration": state.duration,
        "volume": state.volume,
        "muted": state.muted,
        "speed": state.speed,
        "playlist_id": state.playlist_id,
        "performance_profile": state.performance_profile.value,
        "color_profile": state.color_profile,
        "last_error": state.last_error,
        "service_pid": state.service_pid,
        "updated_at": _isoformat(state.updated_at),
    }


def state_to_dict(state: EngineState) -> dict[str, Any]:
    return {
        "version": state.version,
        "updated_at": _isoformat(state.updated_at),
        "service_status": state.service_status,
        "mode": state.mode.value,
        "outputs": {
            output: playback_state_to_dict(value)
            for output, value in state.outputs.items()
        },
        "last_error": state.last_error,
    }


def playback_state_from_dict(output: str, data: Any) -> PlaybackState:
    values = data if isinstance(data, dict) else {}
    path = values.get("path")
    return PlaybackState(
        output=output,
        status=_enum(PlaybackStatus, values.get("status"), PlaybackStatus.STOPPED),
        wallpaper_id=values.get("wallpaper_id"),
        path=Path(path) if isinstance(path, str) and path else None,
        position=values.get("position"),
        duration=values.get("duration"),
        volume=values.get("volume"),
        muted=values.get("muted") if isinstance(values.get("muted"), bool) else None,
        speed=values.get("speed"),
        playlist_id=values.get("playlist_id"),
        performance_profile=_enum(
            PerformanceMode, values.get("performance_profile"), PerformanceMode.AUTO
        ),
        color_profile=(
            values["color_profile"]
            if isinstance(values.get("color_profile"), str) else "Original"
        ),
        last_error=(
            values["last_error"]
            if isinstance(values.get("last_error"), str) else None
        ),
        service_pid=(
            values["service_pid"]
            if isinstance(values.get("service_pid"), int) else None
        ),
        updated_at=_datetime(values.get("updated_at")),
    )


def state_from_dict(data: Any) -> EngineState:
    values = data if isinstance(data, dict) else {}
    raw_outputs = values.get("outputs")
    outputs = {
        output: playback_state_from_dict(output, output_state)
        for output, output_state in raw_outputs.items()
        if isinstance(output, str) and isinstance(output_state, dict)
    } if isinstance(raw_outputs, dict) else {}
    return EngineState(
        version=(
            values["version"]
            if isinstance(values.get("version"), int) else STATE_VERSION
        ),
        updated_at=_datetime(values.get("updated_at")),
        service_status=(
            values["service_status"]
            if values.get("service_status") in {"starting", "running", "stopped", "error"}
            else "stopped"
        ),
        mode=_enum(OutputMode, values.get("mode"), OutputMode.INDEPENDENT),
        outputs=outputs,
        last_error=(values["last_error"] if isinstance(values.get("last_error"), str) else None),
    )


def read_state(paths: EnginePaths | None = None) -> EngineState:
    engine_paths = paths or EnginePaths.from_environment()
    try:
        data = json.loads(engine_paths.state_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return EngineState()
    except (OSError, json.JSONDecodeError) as error:
        LOGGER.warning("Unable to read runtime state %s: %s", engine_paths.state_file, error)
        return EngineState(last_error=str(error))
    return state_from_dict(data)


def _atomic_write(data: dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.parent.chmod(0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=f".{destination.name}-", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def write_state(state: EngineState, paths: EnginePaths | None = None) -> None:
    engine_paths = paths or EnginePaths.from_environment()
    _atomic_write(state_to_dict(state), engine_paths.state_file)


class StateStore:
    """Serialize all in-process runtime mutations and snapshot writes."""

    def __init__(self, paths: EnginePaths | None = None, state: EngineState | None = None):
        self.paths = paths or EnginePaths.from_environment()
        self._state = state or EngineState()
        self._lock = threading.RLock()

    def snapshot(self) -> EngineState:
        with self._lock:
            return deepcopy(self._state)

    def as_dict(self) -> dict[str, Any]:
        return state_to_dict(self.snapshot())

    def _commit(self) -> None:
        self._state.updated_at = utc_now()
        write_state(self._state, self.paths)

    def touch_state(self) -> None:
        with self._lock:
            self._commit()

    def set_service_status(self, status: str, error: str | None = None) -> None:
        if status not in {"starting", "running", "stopped", "error"}:
            raise ValueError("invalid service status")
        with self._lock:
            self._state.service_status = status
            self._state.last_error = error
            self._commit()

    def update_output(self, output: str, value: PlaybackState | None = None, **changes) -> None:
        with self._lock:
            current = value or self._state.outputs.get(output) or PlaybackState(output=output)
            if current.output != output:
                raise ValueError("output state does not match output name")
            for key, change in changes.items():
                if not hasattr(current, key) or key == "output":
                    raise ValueError(f"unknown output state field: {key}")
                setattr(current, key, change)
            current.updated_at = utc_now()
            self._state.outputs[output] = current
            self._commit()

    def remove_output(self, output: str) -> bool:
        with self._lock:
            removed = self._state.outputs.pop(output, None) is not None
            if removed:
                self._commit()
            return removed

    def set_output_error(self, output: str, error: str) -> None:
        self.update_output(output, status=PlaybackStatus.ERROR, last_error=error)

    def clear_output_error(self, output: str) -> None:
        with self._lock:
            current = self._state.outputs.get(output)
            if current is None:
                return
            current.last_error = None
            if current.status == PlaybackStatus.ERROR:
                current.status = PlaybackStatus.STOPPED
            current.updated_at = utc_now()
            self._commit()
