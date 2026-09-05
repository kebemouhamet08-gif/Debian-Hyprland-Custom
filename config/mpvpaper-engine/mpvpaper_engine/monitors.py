"""Hyprland monitor discovery and multi-output policy without polling."""

from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
from typing import Callable

from .config import EngineConfig, validate_output_name
from .models import OutputMode, PlaybackStatus
from .playback import PlaybackController, PlaybackError
from .state import StateStore


HYPRCTL_TIMEOUT = 3.0
SYNC_DRIFT_THRESHOLD = 0.2
SYNC_CHECK_INTERVAL = 7.0


class MonitorError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MonitorInfo:
    name: str
    width: int | None = None
    height: int | None = None
    refresh_rate: float | None = None
    x: int | None = None
    y: int | None = None
    scale: float | None = None
    focused: bool = False


def detect_monitors(runner: Callable = subprocess.run) -> list[MonitorInfo]:
    try:
        result = runner(
            ["hyprctl", "-j", "monitors", "all"],
            capture_output=True, text=True, timeout=HYPRCTL_TIMEOUT, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MonitorError(str(error)) from error
    if result.returncode != 0:
        raise MonitorError(result.stderr.strip() or "hyprctl monitors failed")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise MonitorError("hyprctl returned invalid JSON") from error
    if not isinstance(data, list):
        raise MonitorError("hyprctl monitor response is not a list")
    monitors = []
    for item in data:
        if not isinstance(item, dict) or not validate_output_name(item.get("name")):
            continue
        monitors.append(MonitorInfo(
            name=item["name"],
            width=item.get("width") if isinstance(item.get("width"), int) else None,
            height=item.get("height") if isinstance(item.get("height"), int) else None,
            refresh_rate=(
                float(item["refreshRate"])
                if isinstance(item.get("refreshRate"), (int, float)) else None
            ),
            x=item.get("x") if isinstance(item.get("x"), int) else None,
            y=item.get("y") if isinstance(item.get("y"), int) else None,
            scale=(
                float(item["scale"])
                if isinstance(item.get("scale"), (int, float)) else None
            ),
            focused=item.get("focused") is True,
        ))
    return monitors


class MonitorManager:
    def __init__(
        self,
        config: EngineConfig,
        playback: PlaybackController | None = None,
        state: StateStore | None = None,
    ):
        self.config = config
        self.playback = playback
        self.state = state

    def reconcile(self, monitors: list[MonitorInfo]) -> dict[str, str]:
        connected = {monitor.name for monitor in monitors}
        names = connected | set(self.config.outputs)
        return {
            output: "available" if output in connected else "unavailable"
            for output in sorted(names) if output != "*"
        }

    def handle_hotplug(
        self,
        previous: list[MonitorInfo],
        current: list[MonitorInfo],
    ) -> dict[str, list[str]]:
        before = {monitor.name for monitor in previous}
        after = {monitor.name for monitor in current}
        disconnected = sorted(before - after)
        reconnected = sorted(after - before)
        if self.state is not None:
            for output in disconnected:
                if output in self.config.outputs:
                    self.state.update_output(output, status=PlaybackStatus.UNAVAILABLE)
        restored = []
        if self.playback is not None and self.config.mode != OutputMode.DISABLED:
            for output in reconnected:
                profile = self.config.outputs.get(output)
                if not profile or not profile.get("autostart") or not profile.get("wallpaper"):
                    continue
                self.playback.play(output, profile["wallpaper"])
                restored.append(output)
        return {
            "disconnected": disconnected,
            "reconnected": reconnected,
            "restored": restored,
        }

    def set_mode(self, mode: OutputMode | str) -> OutputMode:
        try:
            selected = mode if isinstance(mode, OutputMode) else OutputMode(mode)
        except ValueError as error:
            raise ValueError("invalid output mode") from error
        self.config.mode = selected
        return selected

    def targets(self, monitors: list[MonitorInfo]) -> list[str]:
        if self.config.mode == OutputMode.DISABLED:
            return []
        connected = [monitor.name for monitor in monitors]
        if self.config.mode == OutputMode.SAME:
            return ["*"] if connected else []
        return [name for name in connected if name in self.config.outputs]

    def correct_sync_drift(self, monitors: list[MonitorInfo]) -> dict[str, float]:
        if self.config.mode != OutputMode.SYNC:
            raise MonitorError("sync correction requires SYNC mode")
        if self.playback is None:
            raise MonitorError("playback controller is unavailable")
        outputs = self.targets(monitors)
        if len(outputs) < 2:
            return {}
        leader = outputs[0]
        leader_state = self.playback.get_state(leader)
        if leader_state.position is None:
            return {}
        corrected = {}
        for output in outputs[1:]:
            try:
                state = self.playback.get_state(output)
                if state.position is None:
                    continue
                drift = state.position - leader_state.position
                if abs(drift) > SYNC_DRIFT_THRESHOLD:
                    self.playback.seek(output, leader_state.position)
                    corrected[output] = drift
            except PlaybackError:
                continue
        return corrected
