"""Coordinate mapping for the HUD editor canvas.

This module only maps the editor viewport; safe-area and collision decisions
remain owned by the HUD positioning engine.
"""

from __future__ import annotations


def canvas_transform(monitor: dict, width: float, height: float) -> tuple[float, float, float]:
    monitor_width = max(1.0, float(monitor["width"]))
    monitor_height = max(1.0, float(monitor["height"]))
    scale = min(width / monitor_width, height / monitor_height)
    return (
        (width - monitor_width * scale) / 2,
        (height - monitor_height * scale) / 2,
        scale,
    )


def normalized_from_canvas(
    x: float, y: float, monitor: dict, width: float, height: float
) -> tuple[float, float]:
    origin_x, origin_y, scale = canvas_transform(monitor, width, height)
    normalized_x = (x - origin_x) / (monitor["width"] * scale)
    normalized_y = (y - origin_y) / (monitor["height"] * scale)
    return (
        max(0.0, min(1.0, normalized_x)),
        max(0.0, min(1.0, normalized_y)),
    )


def canvas_from_normalized(
    x: float, y: float, monitor: dict, width: float, height: float
) -> tuple[float, float]:
    origin_x, origin_y, scale = canvas_transform(monitor, width, height)
    return (
        origin_x + x * monitor["width"] * scale,
        origin_y + y * monitor["height"] * scale,
    )
