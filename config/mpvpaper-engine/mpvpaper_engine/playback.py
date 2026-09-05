"""Validated playback control through MPV IPC with a systemd fallback."""

from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path
import re
import socket
import time
from typing import Any

from .config import (
    COLOR_DEFAULTS,
    COLOR_KEYS,
    EngineConfig,
    bounded_number,
    effective_output_config,
    validate_output_name,
)
from .models import ColorProfile, PerformanceMode, PlaybackState, PlaybackStatus
from .hud import HudManager
from .paths import EnginePaths
from .profiles import effective_settings, mpv_option_fragments
from .state import StateStore
from .systemd import SystemdManager


MPV_TIMEOUT = 2.0
MEDIA_EXTENSIONS = {
    ".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v",
    ".jpg", ".jpeg", ".png", ".webp", ".avif", ".bmp",
}


class PlaybackError(RuntimeError):
    pass


class MpvUnavailableError(PlaybackError):
    pass


class MpvClient:
    def __init__(self, socket_path: Path, timeout: float = MPV_TIMEOUT):
        self.socket_path = Path(socket_path)
        self.timeout = timeout
        self._request_id = 1

    def command(self, *command: Any) -> dict[str, Any]:
        request_id = self._request_id
        self._request_id += 1
        payload = json.dumps({
            "command": list(command), "request_id": request_id,
        }, separators=(",", ":")).encode() + b"\n"
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self.timeout)
                client.connect(str(self.socket_path))
                client.sendall(payload)
                line = client.makefile("rb").readline(1024 * 1024)
        except (FileNotFoundError, ConnectionRefusedError, socket.timeout, OSError) as error:
            raise MpvUnavailableError(f"MPV socket unavailable: {self.socket_path}") from error
        try:
            response = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PlaybackError("invalid MPV IPC response") from error
        if not isinstance(response, dict) or response.get("error") != "success":
            message = response.get("error", "MPV command failed") if isinstance(response, dict) else "MPV command failed"
            raise PlaybackError(str(message))
        return response

    def get_property(self, name: str) -> Any:
        return self.command("get_property", name).get("data")

    def set_property(self, name: str, value: Any) -> None:
        self.command("set_property", name, value)

    def loadfile(self, path: Path) -> None:
        self.command("loadfile", str(Path(path)), "replace")

    def seek(self, seconds: float, mode: str = "absolute") -> None:
        if mode not in {"absolute", "relative"}:
            raise ValueError("invalid seek mode")
        self.command("seek", seconds, mode)


def _is_transient_property_unavailable(error: PlaybackError) -> bool:
    message = str(error).casefold()
    return "property unavailable" in message or "property is unavailable" in message


def _normalized_local_path(value: Any) -> Path | None:
    if not isinstance(value, (str, Path)):
        return None
    text = str(value)
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", text):
        return None
    return Path(text).expanduser().resolve(strict=False)


def _wait_for_media_path(
    client: MpvClient,
    expected: Path,
    *,
    timeout: float = 3.0,
    interval: float = 0.075,
    monotonic=time.monotonic,
    sleep=time.sleep,
) -> str:
    expected_path = _normalized_local_path(expected)
    if expected_path is None:
        raise ValueError("expected media must be a local path")
    deadline = monotonic() + timeout
    last_value = None
    transient_error = None
    while monotonic() < deadline:
        try:
            last_value = client.get_property("path")
            transient_error = None
        except PlaybackError as error:
            if not _is_transient_property_unavailable(error):
                raise
            transient_error = error
        else:
            if _normalized_local_path(last_value) == expected_path:
                return str(last_value)
        remaining = deadline - monotonic()
        if remaining > 0:
            sleep(min(interval, remaining))
    detail = str(transient_error) if transient_error else f"last path: {last_value!r}"
    raise PlaybackError(f"timed out waiting for MPV media {expected_path} ({detail})")


def _socket_suffix(output: str) -> str:
    return "all" if output == "*" else re.sub(r"[^A-Za-z0-9_.-]", "-", output)


def mpv_socket_candidates(paths: EnginePaths, output: str) -> tuple[Path, ...]:
    if not validate_output_name(output):
        raise ValueError("invalid output name")
    canonical = paths.mpv_socket(output)
    legacy = paths.runtime_home / f"{_socket_suffix(output)}.sock"
    return (canonical, legacy) if canonical != legacy else (canonical,)


def color_filter(values: dict[str, Any]) -> str:
    temperature = bounded_number(values.get("temperature"), 6500, 1000, 40000)
    channels = {
        name: bounded_number(values.get(f"{name}_balance"), 0, -100, 100) / 100
        for name in ("red", "green", "blue")
    }
    return (
        f"lavfi=[colortemperature=temperature={temperature},"
        f"colorbalance=rm={channels['red']:.2f}:gm={channels['green']:.2f}:"
        f"bm={channels['blue']:.2f}]"
    )


class PlaybackController:
    def __init__(
        self,
        config: EngineConfig,
        paths: EnginePaths | None = None,
        state: StateStore | None = None,
        systemd: SystemdManager | None = None,
    ):
        self.config = config
        self.paths = paths or EnginePaths.from_environment()
        self.state = state
        self.systemd = systemd or SystemdManager()
        self.hud = HudManager(self.paths.cache_home, self.paths.config_home)
        self.hud.configure(self.config.ui.get("hud", {}))

    def _validate_output(self, output: str) -> None:
        if not validate_output_name(output):
            raise ValueError("invalid output name")

    def _profile(self, output: str) -> dict[str, Any]:
        self._validate_output(output)
        return effective_output_config(self.config, output)

    def _client(self, output: str) -> MpvClient:
        candidates = mpv_socket_candidates(self.paths, output)
        existing = next((path for path in candidates if path.is_socket()), candidates[0])
        return MpvClient(existing)

    def _state_update(self, output: str, **changes) -> None:
        if self.state is not None:
            self.state.update_output(output, **changes)

    def _mpv_options(self, output: str, profile: dict[str, Any]) -> str:
        socket_path = self.paths.mpv_socket(output)
        options = [
            "load-scripts=no", "terminal=no",
            f"input-ipc-server={socket_path}",
            f"speed={profile['speed']}",
            *(f"{key}={int(profile[key])}" for key in (
                "brightness", "contrast", "gamma", "saturation", "hue"
            )),
            f"vf={color_filter(profile)}",
            *self._fit_options(profile.get("fit_mode", "cover")),
            "image-display-duration=inf", "keep-open=yes",
        ]
        hud_file = self.hud.render(output)
        if hud_file is not None:
            options.extend([f"sub-files={hud_file}", "sub-auto=no"])
        if profile.get("loop", True):
            options.append("loop-file=inf")
        performance = effective_settings(profile.get("performance_profile", "auto"))
        options.extend(
            option for option in mpv_option_fragments(performance)
            if not (
                profile.get("hardware_decode", "auto") == "disabled"
                and option.startswith("hwdec=")
            )
        )
        if profile.get("muted", True) or int(profile.get("volume", 0)) <= 0:
            options.append("no-audio")
        else:
            options.extend(["audio=yes", f"volume={int(profile['volume'])}"])
        return " ".join(options)

    @staticmethod
    def _fit_options(mode: str) -> list[str]:
        values = {
            "cover": ["video-unscaled=no", "keepaspect=yes", "panscan=1.0"],
            "contain": ["video-unscaled=no", "keepaspect=yes", "panscan=0.0"],
            "stretch": ["video-unscaled=no", "keepaspect=no", "panscan=0.0"],
        }
        if mode not in values:
            raise ValueError("invalid fit mode")
        return values[mode]

    def play(self, output: str, wallpaper: Path) -> str:
        profile = self._profile(output)
        wallpaper = Path(wallpaper).expanduser().resolve()
        if not wallpaper.is_file() or wallpaper.suffix.casefold() not in MEDIA_EXTENSIONS:
            raise ValueError("wallpaper is missing or unsupported")
        client = self._client(output)
        try:
            client.loadfile(wallpaper)
            _wait_for_media_path(client, wallpaper)
            self._apply_live_profile(client, profile)
            self._apply_hud(client, output)
            strategy = "loadfile"
        except PlaybackError:
            self.systemd.stop_output(output)
            self.systemd.start_output(
                output, wallpaper, self._mpv_options(output, profile),
                auto_pause=bool(profile.get("auto_pause", True)),
            )
            strategy = "systemd"
        self._state_update(
            output, path=wallpaper, status=PlaybackStatus.PLAYING,
            position=0.0, duration=None, last_error=None,
        )
        return strategy

    def _apply_hud(self, client: MpvClient, output: str) -> None:
        hud_file = self.hud.render(output)
        if hud_file is None:
            return
        client.set_property("sub-files", [str(hud_file)])
        if hasattr(client, "command"):
            try:
                client.command("sub-reload")
            except PlaybackError:
                pass

    def refresh_hud(self, output: str) -> bool:
        hud_file = self.hud.render(output)
        if hud_file is None:
            return False
        client = self._client(output)
        client.set_property("sub-files", [str(hud_file)])
        if hasattr(client, "command"):
            try:
                client.command("sub-reload")
            except PlaybackError:
                return False
        return True

    def stop(self, output: str) -> None:
        self._validate_output(output)
        self.systemd.stop_output(output)
        self._state_update(output, status=PlaybackStatus.STOPPED, position=None)

    def pause(self, output: str) -> None:
        self._client(output).set_property("pause", True)
        self._state_update(output, status=PlaybackStatus.PAUSED)

    def resume(self, output: str) -> None:
        self._client(output).set_property("pause", False)
        self._state_update(output, status=PlaybackStatus.PLAYING)

    def toggle_pause(self, output: str) -> bool:
        client = self._client(output)
        paused = not bool(client.get_property("pause"))
        client.set_property("pause", paused)
        self._state_update(
            output, status=PlaybackStatus.PAUSED if paused else PlaybackStatus.PLAYING
        )
        return paused

    def restart(self, output: str) -> None:
        self._validate_output(output)
        self.systemd.restart_output(output)
        self._state_update(output, status=PlaybackStatus.LOADING, position=None)

    def set_performance_profile(self, output: str, mode: PerformanceMode | str) -> str:
        """Apply a performance profile to one running output without persisting config."""
        self._validate_output(output)
        try:
            selected = mode if isinstance(mode, PerformanceMode) else PerformanceMode(mode)
        except ValueError as error:
            raise ValueError("invalid performance profile") from error
        profile = self.config.outputs.setdefault(output, {})
        profile["performance_profile"] = selected.value
        current = self.state.snapshot().outputs.get(output) if self.state is not None else None
        path = current.path if current is not None else None
        if path is None:
            configured = self._profile(output).get("wallpaper")
            path = Path(configured) if isinstance(configured, str) and configured else None
        if path is not None and path.is_file():
            effective = self._profile(output)
            self.systemd.stop_output(output)
            self.systemd.start_output(
                output, path, self._mpv_options(output, effective),
                auto_pause=bool(effective.get("auto_pause", True)),
            )
        self._state_update(output, performance_profile=selected)
        return selected.value

    def seek(self, output: str, seconds: float) -> None:
        seconds = self._finite_number(seconds, minimum=0)
        self._client(output).seek(seconds, "absolute")
        self._state_update(output, position=seconds)

    def seek_relative(self, output: str, delta: float) -> None:
        delta = self._finite_number(delta)
        self._client(output).seek(delta, "relative")

    def set_volume(self, output: str, volume: int) -> int:
        value = bounded_number(volume, 0, 0, 100)
        self._client(output).set_property("volume", value)
        self._state_update(output, volume=value)
        return value

    def set_mute(self, output: str, muted: bool) -> None:
        if not isinstance(muted, bool):
            raise ValueError("muted must be boolean")
        self._client(output).set_property("mute", muted)
        self._state_update(output, muted=muted)

    def set_speed(self, output: str, speed: float) -> float:
        value = bounded_number(speed, 1.0, 0.1, 5.0, float)
        self._client(output).set_property("speed", value)
        self._state_update(output, speed=value)
        return value

    def set_loop(self, output: str, enabled: bool) -> None:
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be boolean")
        self._client(output).set_property("loop-file", "inf" if enabled else "no")

    def set_fit(self, output: str, mode: str) -> None:
        client = self._client(output)
        options = self._fit_options(mode)
        for option in options:
            name, value = option.split("=", 1)
            converted: Any = float(value) if name == "panscan" else value == "yes"
            client.set_property(name, converted)

    def set_color(self, output: str, color_profile: ColorProfile | dict[str, Any]) -> None:
        values = asdict(color_profile) if isinstance(color_profile, ColorProfile) else color_profile
        if not isinstance(values, dict):
            raise ValueError("invalid color profile")
        normalized = {}
        for key in COLOR_KEYS:
            low, high = (1000, 40000) if key == "temperature" else (-100, 100)
            normalized[key] = bounded_number(values.get(key), COLOR_DEFAULTS[key], low, high)
        client = self._client(output)
        for key in ("brightness", "contrast", "gamma", "saturation", "hue"):
            client.set_property(key, normalized[key])
        client.set_property("vf", color_filter(normalized))
        profile_name = values.get("name") if isinstance(values.get("name"), str) else "Custom"
        self._state_update(output, color_profile=profile_name)

    def get_state(self, output: str) -> PlaybackState:
        client = self._client(output)
        path = client.get_property("path")
        paused = client.get_property("pause")
        position = client.get_property("time-pos")
        duration = client.get_property("duration")
        volume = client.get_property("volume")
        muted = client.get_property("mute")
        speed = client.get_property("speed")
        state = PlaybackState(
            output=output,
            status=PlaybackStatus.PAUSED if paused else PlaybackStatus.PLAYING,
            path=Path(path) if isinstance(path, str) and path else None,
            position=position if isinstance(position, (int, float)) else None,
            duration=duration if isinstance(duration, (int, float)) else None,
            volume=int(volume) if isinstance(volume, (int, float)) else None,
            muted=muted if isinstance(muted, bool) else None,
            speed=float(speed) if isinstance(speed, (int, float)) else None,
            performance_profile=PerformanceMode.AUTO,
        )
        if self.state is not None:
            self.state.update_output(output, value=state)
        return state

    def _apply_live_profile(self, client: MpvClient, profile: dict[str, Any]) -> None:
        client.set_property("speed", profile["speed"])
        client.set_property("volume", profile["volume"])
        client.set_property("mute", profile.get("muted", True))
        client.set_property("loop-file", "inf" if profile.get("loop", True) else "no")
        self.set_fit_via_client(client, profile.get("fit_mode", "cover"))
        normalized = {key: profile[key] for key in COLOR_KEYS}
        for key in ("brightness", "contrast", "gamma", "saturation", "hue"):
            client.set_property(key, normalized[key])
        client.set_property("vf", color_filter(normalized))

    def set_fit_via_client(self, client: MpvClient, mode: str) -> None:
        for option in self._fit_options(mode):
            name, value = option.split("=", 1)
            converted: Any = float(value) if name == "panscan" else value == "yes"
            client.set_property(name, converted)

    @staticmethod
    def _finite_number(value: Any, minimum: float | None = None) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError("value must be numeric") from error
        if not math.isfinite(number) or (minimum is not None and number < minimum):
            raise ValueError("numeric value is outside allowed range")
        return number
