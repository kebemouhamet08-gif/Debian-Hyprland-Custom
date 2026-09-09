"""Pure geometry helpers used by the desktop HUD."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def intersects(self, other: "Rect") -> bool:
        return (
            self.x < other.right and self.right > other.x
            and self.y < other.bottom and self.bottom > other.y
        )

    def moved(self, x: float, y: float) -> "Rect":
        return Rect(x, y, self.width, self.height)


def clamp_rect(rect: Rect, bounds: Rect) -> Rect:
    width = min(rect.width, bounds.width)
    height = min(rect.height, bounds.height)
    return Rect(
        min(max(rect.x, bounds.x), bounds.right - width),
        min(max(rect.y, bounds.y), bounds.bottom - height),
        width,
        height,
    )


def safe_area(screen: Rect, obstacles: list[Rect], margin: float = 0) -> Rect:
    """Return the largest simple inset area occupied by edge-attached surfaces."""
    left = screen.x + margin
    top = screen.y + margin
    right = screen.right - margin
    bottom = screen.bottom - margin
    for obstacle in obstacles:
        # Full-screen shell/overview surfaces are not reserved edge panels.
        if obstacle.width >= screen.width * .8 and obstacle.height >= screen.height * .8:
            continue
        if obstacle.right <= screen.x or obstacle.x >= screen.right:
            continue
        if obstacle.bottom <= screen.y or obstacle.y >= screen.bottom:
            continue
        horizontal = obstacle.width >= obstacle.height
        edge_distance = 64
        if horizontal and obstacle.y <= screen.y + edge_distance and obstacle.bottom > top:
            top = max(top, min(obstacle.bottom + margin, screen.bottom))
        if not horizontal and obstacle.x <= screen.x + edge_distance and obstacle.right > left:
            left = max(left, min(obstacle.right + margin, screen.right))
        if horizontal and obstacle.bottom >= screen.bottom - edge_distance and obstacle.y < bottom:
            bottom = min(bottom, max(obstacle.y - margin, screen.y))
        if not horizontal and obstacle.right >= screen.right - edge_distance and obstacle.x < right:
            right = min(right, max(obstacle.x - margin, screen.x))
    return Rect(left, top, max(0, right - left), max(0, bottom - top))


def snap_position(x: float, y: float, bounds: Rect, threshold: float = 18) -> tuple[float, float]:
    candidates_x = (bounds.x, bounds.right)
    candidates_y = (bounds.y, bounds.bottom)
    if any(abs(x - candidate) <= threshold for candidate in candidates_x):
        x = min(candidates_x, key=lambda candidate: abs(x - candidate))
    if any(abs(y - candidate) <= threshold for candidate in candidates_y):
        y = min(candidates_y, key=lambda candidate: abs(y - candidate))
    return x, y


def nearest_free_position(
    desired: Rect,
    bounds: Rect,
    obstacles: list[Rect],
    step: float = 8,
) -> Rect:
    """Find the closest clamped position that does not overlap an obstacle."""
    desired = clamp_rect(desired, bounds)
    if not any(desired.intersects(obstacle) for obstacle in obstacles):
        return desired
    step = max(1, float(step))
    max_radius = int(max(bounds.width, bounds.height) / step) + 1
    for radius in range(1, max_radius + 1):
        distance = radius * step
        candidates = (
            (desired.x - distance, desired.y), (desired.x + distance, desired.y),
            (desired.x, desired.y - distance), (desired.x, desired.y + distance),
        )
        for x, y in candidates:
            candidate = clamp_rect(desired.moved(x, y), bounds)
            if not any(candidate.intersects(obstacle) for obstacle in obstacles):
                return candidate
    return desired


def resolve_position(
    x: float,
    y: float,
    screen: Rect,
    hud_size: tuple[float, float],
    bounds: Rect | None = None,
    obstacles: list[Rect] | None = None,
    snap: bool = False,
) -> tuple[float, float]:
    """Resolve normalized HUD coordinates into a safe top-left position."""
    bounds = bounds or screen
    hud_width, hud_height = hud_size
    desired = Rect(
        screen.x + screen.width * x - hud_width / 2,
        screen.y + screen.height * y - hud_height / 2,
        hud_width,
        hud_height,
    )
    if snap:
        snapped_x, snapped_y = snap_position(desired.x, desired.y, bounds)
        desired = desired.moved(snapped_x, snapped_y)
    resolved = nearest_free_position(desired, bounds, obstacles or [])
    return (
        (resolved.x + hud_width / 2 - screen.x) / screen.width,
        (resolved.y + hud_height / 2 - screen.y) / screen.height,
    )
