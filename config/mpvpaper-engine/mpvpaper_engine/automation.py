"""Event-driven Smart Pause policy with composable pause reasons."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .playback import PlaybackController


class AutomationAction(str, Enum):
    CONTINUE = "continue"
    REDUCE = "reduce"
    PAUSE = "pause"
    STOP = "stop"


class AutomationReason(str, Enum):
    FULLSCREEN = "fullscreen"
    LOCK = "lock"
    SUSPEND = "suspend"
    DPMS = "dpms"
    BATTERY = "battery"
    POWER_SAVER = "power_saver"


@dataclass(frozen=True, slots=True)
class AutomationEvent:
    reason: AutomationReason
    active: bool


@dataclass(slots=True)
class OutputAutomationState:
    paused_by: set[AutomationReason] = field(default_factory=set)
    reduced_by: set[AutomationReason] = field(default_factory=set)
    stopped_by: set[AutomationReason] = field(default_factory=set)
    original_speed: float | None = None


DEFAULT_POLICY = {
    AutomationReason.FULLSCREEN: AutomationAction.PAUSE,
    AutomationReason.LOCK: AutomationAction.PAUSE,
    AutomationReason.SUSPEND: AutomationAction.PAUSE,
    AutomationReason.DPMS: AutomationAction.PAUSE,
    AutomationReason.BATTERY: AutomationAction.REDUCE,
    AutomationReason.POWER_SAVER: AutomationAction.REDUCE,
}


class SmartPauseController:
    def __init__(
        self,
        playback: PlaybackController,
        *,
        policy: dict[AutomationReason, AutomationAction] | None = None,
        reduced_speed: float = 0.5,
    ):
        self.playback = playback
        self.policy = {**DEFAULT_POLICY, **(policy or {})}
        self.reduced_speed = max(0.1, min(float(reduced_speed), 1.0))
        self.outputs: dict[str, OutputAutomationState] = {}

    def state_for(self, output: str) -> OutputAutomationState:
        return self.outputs.setdefault(output, OutputAutomationState())

    def handle(self, output: str, event: AutomationEvent) -> OutputAutomationState:
        state = self.state_for(output)
        action = self.policy.get(event.reason, AutomationAction.CONTINUE)
        collection = {
            AutomationAction.PAUSE: state.paused_by,
            AutomationAction.REDUCE: state.reduced_by,
            AutomationAction.STOP: state.stopped_by,
        }.get(action)
        if collection is None:
            return state
        was_active = bool(collection)
        if event.active:
            collection.add(event.reason)
            if action == AutomationAction.PAUSE and not was_active:
                self.playback.pause(output)
            elif action == AutomationAction.REDUCE and not was_active:
                current = self.playback.get_state(output)
                state.original_speed = current.speed or 1.0
                self.playback.set_speed(output, self.reduced_speed)
            elif action == AutomationAction.STOP and not was_active:
                self.playback.stop(output)
        else:
            collection.discard(event.reason)
            if action == AutomationAction.PAUSE and was_active and not collection:
                self.playback.resume(output)
            elif action == AutomationAction.REDUCE and was_active and not collection:
                self.playback.set_speed(output, state.original_speed or 1.0)
                state.original_speed = None
            # STOP is intentionally not auto-restored without an explicit playback request.
        return state


def parse_hyprland_event(line: str) -> AutomationEvent | None:
    event, separator, payload = line.strip().partition(">>")
    if not separator:
        return None
    if event == "fullscreen":
        return AutomationEvent(AutomationReason.FULLSCREEN, payload == "1")
    if event == "lock":
        return AutomationEvent(AutomationReason.LOCK, payload in {"1", "locked"})
    if event == "monitorremoved":
        return AutomationEvent(AutomationReason.DPMS, True)
    if event == "monitoradded":
        return AutomationEvent(AutomationReason.DPMS, False)
    return None


def logind_event(*, locked: bool | None = None, preparing_for_sleep: bool | None = None):
    if locked is not None:
        return AutomationEvent(AutomationReason.LOCK, bool(locked))
    if preparing_for_sleep is not None:
        return AutomationEvent(AutomationReason.SUSPEND, bool(preparing_for_sleep))
    return None


def upower_event(*, on_battery: bool, power_saver: bool = False) -> list[AutomationEvent]:
    return [
        AutomationEvent(AutomationReason.BATTERY, bool(on_battery)),
        AutomationEvent(AutomationReason.POWER_SAVER, bool(power_saver)),
    ]


def dpms_event(active: Any) -> AutomationEvent:
    if not isinstance(active, bool):
        raise ValueError("DPMS state must be boolean")
    return AutomationEvent(AutomationReason.DPMS, not active)
