"""Shared desktop/editor layout in logical screen pixels, independent of MPV."""

from datetime import datetime
import re

from .hud import settings_from_config
from .hud_positioning import Rect, safe_area


ANCHORS = {
    "top-left": (0, 0), "top": (.5, 0), "top-right": (1, 0),
    "left": (0, .5), "center": (.5, .5), "right": (1, .5),
    "bottom-left": (0, 1), "bottom": (.5, 1), "bottom-right": (1, 1),
}
PALETTE = {"text": "#FFFFFF", "muted": "#CCCCCC", "accent": "#FF5577", "lines": "#CCCCCC"}


def logical_screen(monitor):
    scale = monitor.scale if monitor.scale and monitor.scale > 0 else 1
    width, height = monitor.width, monitor.height
    if getattr(monitor, "transform", 0) in (1, 3, 5, 7):
        width, height = height, width
    return Rect(monitor.x or 0, monitor.y or 0,
                width / scale, height / scale)


def geometry(data, screen, panels=()):
    settings = settings_from_config(data)
    width, height = 620 * settings.scale, 560 * settings.scale
    ax, ay = ANCHORS[settings.anchor]
    area = (safe_area(screen, list(panels), settings.safe_margin)
            if settings.avoid_layers else screen)
    x = screen.x + settings.x * screen.width - ax * width
    y = screen.y + settings.y * screen.height - ay * height
    requested = (x, y)
    # Keep requested scale intact even when the widget exceeds the available area.
    if settings.avoid_layers:
        x = max(area.x, min(x, area.right - width))
        y = max(area.y, min(y, area.bottom - height))
    snapped = False
    if settings.snap:
        for axis, value, start, end, size in (
            (0, x, area.x, area.right, width),
            (1, y, area.y, area.bottom, height),
        ):
            candidates = (start, (start + end - size) / 2, end - size)
            nearest = min(candidates, key=lambda candidate: abs(candidate - value))
            if abs(nearest - value) <= 8:
                snapped |= nearest != value
                if axis == 0:
                    x = nearest
                else:
                    y = nearest
    return {
        "rect": Rect(x, y, width, height), "safe_area": area,
        "resolved": {"x": (x + ax * width - screen.x) / screen.width,
                     "y": (y + ay * height - screen.y) / screen.height},
        "collision": settings.avoid_layers and requested != (x, y),
        "snapped": snapped,
        "limited": width > area.width or height > area.height,
    }


def colors(data, system=None):
    settings = settings_from_config(data)
    palette = {**PALETTE, **(system or {})}
    if settings.color_mode == "custom":
        aliases = {"primary": "text", "secondary": "muted", "line": "lines"}
        for key, value in (settings.custom_colors or {}).items():
            if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                palette[aliases.get(key, key)] = value
    return palette


def entries(data, now=None):
    settings = settings_from_config(data)
    now = now or datetime.now().astimezone()
    english, japanese = ("GOOD MORNING", "おはよう") if 5 <= now.hour < 12 else (
        ("GOOD AFTERNOON", "こんにちは") if 12 <= now.hour < 18 else ("GOOD EVENING", "こんばんは"))
    rows = [
        (settings.greeting, english, 58, -110, "Noto Sans Bold", "text"),
        (settings.day, now.strftime("%a").upper(), 56, -40, "Anurati", "text"),
        (settings.time, now.strftime("%H:%M"), 42, 15, "Noto Sans", "text"),
        (settings.date, now.strftime("%d"), 42, 65, "Noto Sans", "text"),
        (settings.japanese, japanese, 28, 115, "Noto Sans CJK JP", "accent"),
        (bool(settings.username), settings.username, 22, 155, "Noto Sans CJK JP", "muted"),
    ]
    if settings.decorative_lines:
        rows.extend((True, "│", 38, offset, "Noto Sans", "lines")
                    for offset in (-260, -215, 215, 260))
    return [row[1:] for row in rows if row[0]]


def draw(context, data, rect, palette=None):
    """The same Pango renderer is used by GTK3 desktop and GTK4 editor."""
    import gi
    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Pango, PangoCairo

    settings = settings_from_config(data)
    if not settings.enabled:
        return
    palette = colors(data, palette)
    for text, size, offset, family, color in entries(data):
        layout = PangoCairo.create_layout(context)
        PangoCairo.context_set_resolution(layout.get_context(), 96)
        font = Pango.FontDescription(family)
        font.set_absolute_size(size * settings.scale * Pango.SCALE)
        layout.set_font_description(font)
        layout.set_width(round(rect.width * Pango.SCALE))
        layout.set_alignment(Pango.Alignment.CENTER)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        layout.set_single_paragraph_mode(True)
        layout.set_text(text, -1)
        _, height = layout.get_pixel_size()
        value = palette[color]
        rgb = [int(value[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        context.set_source_rgba(*rgb, settings.opacity)
        context.move_to(rect.x, rect.y + rect.height / 2 + offset * settings.scale - height / 2)
        PangoCairo.show_layout(context, layout)
