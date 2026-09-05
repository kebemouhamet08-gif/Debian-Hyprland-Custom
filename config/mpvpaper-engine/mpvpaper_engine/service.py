"""Minimal MPVpaper Engine session service for state and read-only IPC."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import signal
import threading
from typing import Any, Callable

from .config import EngineConfig, load_config, validate_output_name
from .ipc import EngineServer, PROTOCOL_VERSION, RPCError
from .logging import configure_logging
from .models import PerformanceMode, PlaybackState, PlaybackStatus
from .paths import EnginePaths
from .playback import PlaybackController, PlaybackError
from .playback import mpv_socket_candidates
from .state import EngineState, STATE_VERSION, StateStore, playback_state_to_dict
from .systemd import SystemdError


ENGINE_VERSION = "2.0-d3"
LOGGER = logging.getLogger(__name__)


def initial_state_from_config(config: EngineConfig) -> EngineState:
    outputs = {}
    for output, profile in config.outputs.items():
        wallpaper = profile.get("wallpaper")
        performance = profile.get("performance_profile", PerformanceMode.AUTO.value)
        try:
            performance_mode = PerformanceMode(performance)
        except (TypeError, ValueError):
            performance_mode = PerformanceMode.AUTO
        outputs[output] = PlaybackState(
            output=output,
            status=PlaybackStatus.STOPPED,
            path=Path(wallpaper) if isinstance(wallpaper, str) and wallpaper else None,
            position=None,
            duration=None,
            volume=profile.get("volume") if isinstance(profile.get("volume"), int) else None,
            muted=profile.get("muted") if isinstance(profile.get("muted"), bool) else None,
            speed=(
                profile.get("speed")
                if isinstance(profile.get("speed"), (int, float)) else None
            ),
            performance_profile=performance_mode,
            color_profile=(
                profile["color_profile"]
                if isinstance(profile.get("color_profile"), str) else "Original"
            ),
            service_pid=os.getpid(),
        )
    return EngineState(
        mode=config.mode,
        service_status="starting",
        outputs=outputs,
        last_error=config.load_error,
    )


class EngineService:
    def __init__(
        self,
        paths: EnginePaths | None = None,
        config_loader: Callable[[EnginePaths], EngineConfig] = load_config,
    ):
        self.paths = paths or EnginePaths.from_environment()
        self.config = config_loader(self.paths)
        self.state = StateStore(self.paths, initial_state_from_config(self.config))
        self.playback = PlaybackController(self.config, self.paths, self.state)
        self.server = EngineServer(self._methods(), self.paths)
        self._stop_event = threading.Event()
        self._started = False

    def _methods(self):
        return {
            "ping": self._ping,
            "get_state": self._get_state,
            "get_output_state": self._get_output_state,
            "list_outputs": self._list_outputs,
            "get_version": self._get_version,
            "play": self._play,
            "stop": self._stop,
            "pause": self._pause,
            "resume": self._resume,
            "toggle_pause": self._toggle_pause,
            "restart": self._restart,
            "seek": self._seek,
            "seek_relative": self._seek_relative,
            "set_volume": self._set_volume,
            "set_mute": self._set_mute,
            "set_speed": self._set_speed,
            "set_loop": self._set_loop,
            "set_fit": self._set_fit,
            "set_color": self._set_color,
            "set_performance_profile": self._set_performance_profile,
            "get_playback_state": self._get_playback_state,
        }

    @staticmethod
    def _require_empty(params: dict[str, Any]) -> None:
        if params:
            raise RPCError("invalid_params", "This method does not accept parameters")

    def _ping(self, params: dict[str, Any]) -> dict[str, bool]:
        self._require_empty(params)
        return {"pong": True}

    def _get_state(self, params: dict[str, Any]) -> dict[str, Any]:
        self._require_empty(params)
        return self.state.as_dict()

    def _get_output_state(self, params: dict[str, Any]) -> dict[str, Any]:
        if set(params) != {"output"} or not validate_output_name(params.get("output")):
            raise RPCError("invalid_params", "A valid output name is required")
        output = params["output"]
        current = self.state.snapshot().outputs.get(output)
        if current is None:
            raise RPCError("output_not_found", f"Output is not configured: {output}")
        return {"output": output, **playback_state_to_dict(current)}

    def _list_outputs(self, params: dict[str, Any]) -> list[str]:
        self._require_empty(params)
        return sorted(self.state.snapshot().outputs)

    def _get_version(self, params: dict[str, Any]) -> dict[str, Any]:
        self._require_empty(params)
        return {
            "engine": ENGINE_VERSION,
            "protocol": PROTOCOL_VERSION,
            "state": STATE_VERSION,
        }

    @staticmethod
    def _output(params: dict[str, Any], *extra: str) -> str:
        if set(params) != {"output", *extra} or not validate_output_name(params.get("output")):
            raise RPCError("invalid_params", "Invalid playback parameters")
        return params["output"]

    @staticmethod
    def _invoke(operation, *args):
        try:
            return operation(*args)
        except (ValueError, PlaybackError, SystemdError) as error:
            raise RPCError("playback_error", str(error)) from error

    def _play(self, params):
        output = self._output(params, "wallpaper")
        if not isinstance(params["wallpaper"], str) or not params["wallpaper"]:
            raise RPCError("invalid_params", "wallpaper must be a non-empty path")
        strategy = self._invoke(self.playback.play, output, Path(params["wallpaper"]))
        return {"strategy": strategy}

    def _stop(self, params):
        output = self._output(params)
        self._invoke(self.playback.stop, output)
        return {"stopped": True}

    def _pause(self, params):
        output = self._output(params)
        self._invoke(self.playback.pause, output)
        return {"paused": True}

    def _resume(self, params):
        output = self._output(params)
        self._invoke(self.playback.resume, output)
        return {"paused": False}

    def _toggle_pause(self, params):
        output = self._output(params)
        return {"paused": self._invoke(self.playback.toggle_pause, output)}

    def _restart(self, params):
        output = self._output(params)
        self._invoke(self.playback.restart, output)
        return {"restarted": True}

    def _seek(self, params):
        output = self._output(params, "seconds")
        self._invoke(self.playback.seek, output, params["seconds"])
        return {"position": float(params["seconds"])}

    def _seek_relative(self, params):
        output = self._output(params, "delta")
        self._invoke(self.playback.seek_relative, output, params["delta"])
        return {"delta": float(params["delta"])}

    def _set_volume(self, params):
        output = self._output(params, "volume")
        return {"volume": self._invoke(self.playback.set_volume, output, params["volume"])}

    def _set_mute(self, params):
        output = self._output(params, "muted")
        self._invoke(self.playback.set_mute, output, params["muted"])
        return {"muted": params["muted"]}

    def _set_speed(self, params):
        output = self._output(params, "speed")
        return {"speed": self._invoke(self.playback.set_speed, output, params["speed"])}

    def _set_loop(self, params):
        output = self._output(params, "enabled")
        self._invoke(self.playback.set_loop, output, params["enabled"])
        return {"loop": params["enabled"]}

    def _set_fit(self, params):
        output = self._output(params, "mode")
        self._invoke(self.playback.set_fit, output, params["mode"])
        return {"fit": params["mode"]}

    def _set_color(self, params):
        output = self._output(params, "color")
        self._invoke(self.playback.set_color, output, params["color"])
        return {"color": params["color"].get("name", "Custom")}

    def _set_performance_profile(self, params):
        output = self._output(params, "profile")
        profile = self._invoke(
            self.playback.set_performance_profile, output, params["profile"]
        )
        return {"profile": profile}

    def _get_playback_state(self, params):
        output = self._output(params)
        current = self._invoke(self.playback.get_state, output)
        return {"output": output, **playback_state_to_dict(current)}

    def start(self) -> None:
        if self._started:
            raise RuntimeError("Engine service is already started")
        self.server.start()
        try:
            self.state.set_service_status("running", self.config.load_error)
            self._reconcile_running_outputs()
        except Exception:
            self.server.shutdown()
            raise
        self._started = True

    def _reconcile_running_outputs(self) -> None:
        """Reconstruct state once when wallpapers predate the Engine service."""
        for output in self.config.outputs:
            if not any(path.is_socket() for path in mpv_socket_candidates(self.paths, output)):
                continue
            try:
                self.playback.get_state(output)
            except PlaybackError as error:
                LOGGER.warning("Unable to reconstruct %s playback state: %s", output, error)

    def shutdown(self) -> None:
        if not self._started:
            return
        self._stop_event.set()
        try:
            self.server.shutdown()
        finally:
            self.state.set_service_status("stopped", self.config.load_error)
            self._started = False

    def run_forever(self) -> None:
        self.start()
        try:
            self._stop_event.wait()
        finally:
            self.shutdown()

    def request_shutdown(self, _signum=None, _frame=None) -> None:
        self._stop_event.set()


def run_session_service(paths: EnginePaths | None = None) -> None:
    service = EngineService(paths)
    previous = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.signal(signum, service.request_shutdown)
    try:
        service.run_forever()
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def main() -> int:
    configure_logging()
    try:
        run_session_service()
    except Exception as error:
        LOGGER.error("Engine session service failed: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
