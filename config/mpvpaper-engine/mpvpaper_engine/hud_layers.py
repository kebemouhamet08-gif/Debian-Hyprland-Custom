"""Discovery and normalization of Hyprland layer-shell surfaces."""

from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
from typing import Callable, Any

from .hud_positioning import Rect


HYPRCTL_TIMEOUT = 3.0


class HudLayerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class HudLayer:
    monitor: str
    namespace: str
    rect: Rect
    layer: str = ""
    mapped: bool = True

    @property
    def is_panel(self) -> bool:
        name = self.namespace.casefold()
        return any(part in name for part in ("waybar", "dock", "ags", "eww", "panel", "shell"))


def _rect(value: Any) -> Rect | None:
    if not isinstance(value, dict):
        return None
    values = [value.get(key) for key in ("x", "y", "w", "h")]
    if not all(isinstance(item, (int, float)) for item in values):
        return None
    x, y, width, height = values
    if width <= 0 or height <= 0:
        return None
    return Rect(float(x), float(y), float(width), float(height))


def parse_layers(data: Any) -> list[HudLayer]:
    if not isinstance(data, dict):
        raise HudLayerError("hyprctl layer response is not an object")
    layers = []
    for monitor, monitor_data in data.items():
        levels = monitor_data.get("levels", {}) if isinstance(monitor_data, dict) else {}
        if not isinstance(levels, dict):
            continue
        for level, entries in levels.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict) or entry.get("mapped") is False:
                    continue
                rect = _rect(entry.get("geometry")) or _rect(entry)
                namespace = entry.get("namespace", "")
                if rect is not None and isinstance(namespace, str):
                    layers.append(HudLayer(str(monitor), namespace, rect, str(level)))
    return layers


def detect_layers(runner: Callable = subprocess.run) -> list[HudLayer]:
    try:
        result = runner(
            ["hyprctl", "-j", "layers"], capture_output=True, text=True,
            timeout=HYPRCTL_TIMEOUT, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HudLayerError(str(error)) from error
    if result.returncode != 0:
        raise HudLayerError(result.stderr.strip() or "hyprctl layers failed")
    try:
        return parse_layers(json.loads(result.stdout))
    except json.JSONDecodeError as error:
        raise HudLayerError("hyprctl returned invalid layer JSON") from error


def panel_rects(layers: list[HudLayer], monitor: str) -> list[Rect]:
    return [layer.rect for layer in layers if layer.monitor == monitor and layer.is_panel]
