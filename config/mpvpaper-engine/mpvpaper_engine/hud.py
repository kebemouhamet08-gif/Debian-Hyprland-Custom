"""Dynamic ASS desktop HUD rendered by MPV over the wallpaper."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import threading
from typing import Any


@dataclass(frozen=True, slots=True)
class HudSettings:
    enabled: bool = False
    x: float = 0.18
    y: float = 0.30
    scale: float = 1.0
    opacity: float = 1.0
    username: str = "ムハメト・ケベ"
    greeting: bool = True
    day: bool = True
    time: bool = True
    date: bool = True
    japanese: bool = True
    decorative_lines: bool = True


def settings_from_config(data: Any) -> HudSettings:
    source = data if isinstance(data, dict) else {}
    position = source.get("position") if isinstance(source.get("position"), dict) else {}
    elements = source.get("elements") if isinstance(source.get("elements"), dict) else {}
    return HudSettings(
        enabled=source.get("enabled") is True,
        x=max(0.05, min(0.95, float(position.get("x", 0.18)))),
        y=max(0.10, min(0.90, float(position.get("y", 0.30)))),
        scale=max(0.5, min(2.0, float(source.get("scale", 1.0)))),
        opacity=max(0.15, min(1.0, float(source.get("opacity", 1.0)))),
        username=str(source.get("username", "ムハメト・ケベ"))[:80],
        **{name: elements.get(name, True) is not False for name in (
            "greeting", "day", "time", "date", "japanese", "decorative_lines",
        )},
    )


def _ass_color(value: str, fallback: str, alpha: int = 0) -> str:
    match = re.fullmatch(r"#([0-9a-fA-F]{6})", value or "")
    if not match:
        value = fallback
    red, green, blue = (value[index:index + 2] for index in (1, 3, 5))
    return f"&H{alpha:02X}{blue}{green}{red}".upper()


def _palette(path: Path) -> dict[str, str]:
    values = {"text": "#FFFFFF", "muted": "#CCCCCC", "accent": "#FF5577"}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"@define-color\s+(text|muted|accent)\s+(#[0-9a-fA-F]{6});", line)
            if match:
                values[match.group(1)] = match.group(2)
    except OSError:
        pass
    return values


def _monitor_size(output: str) -> tuple[int, int] | None:
    try:
        result = subprocess.run(
            ["hyprctl", "-j", "monitors", "all"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        data = json.loads(result.stdout) if result.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    if not isinstance(data, list):
        return None
    candidates = [
        item for item in data
        if isinstance(item, dict) and (output == "*" or item.get("name") == output)
    ]
    for item in candidates:
        width, height = item.get("width"), item.get("height")
        if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
            return width, height
    return None


def make_ass(width: int, height: int, settings: HudSettings, palette: dict[str, str]) -> str:
    now = datetime.now().astimezone()
    greetings = ((5, 12, "GOOD MORNING", "おはよう"), (12, 18, "GOOD AFTERNOON", "こんにちは"))
    greeting_en, greeting_jp = "GOOD EVENING", "こんばんは"
    for start, end, english, japanese in greetings:
        if start <= now.hour < end:
            greeting_en, greeting_jp = english, japanese
            break
    x, y = int(width * settings.x), int(height * settings.y)
    alpha = max(0, min(255, round((1 - settings.opacity) * 255)))
    primary = _ass_color(palette["text"], "#FFFFFF", alpha)
    secondary = _ass_color(palette["muted"], "#CCCCCC", alpha)
    accent = _ass_color(palette["accent"], "#FF5577", alpha)
    sizes = {
        "normal": round(42 * settings.scale),
        "greeting": round(58 * settings.scale),
        "day": round(56 * settings.scale),
        "japanese": round(28 * settings.scale),
        "username": round(22 * settings.scale),
        "lines": round(38 * settings.scale),
    }
    gap = lambda value: round(value * settings.scale)
    events = []
    if settings.decorative_lines:
        events.extend((
            ("Lines", f"{{\\pos({x},{y - gap(150)})}}│"),
            ("Lines", f"{{\\pos({x},{y - gap(105)})}}│"),
        ))
    if settings.greeting:
        events.append(("Greeting", f"{{\\pos({x},{y})}}{greeting_en}"))
    if settings.day:
        events.append(("Anurati", f"{{\\pos({x},{y + gap(70)})}}{now.strftime('%a').upper()}"))
    if settings.time:
        events.append(("Normal", f"{{\\pos({x},{y + gap(125)})}}{now.strftime('%H:%M')}"))
    if settings.date:
        events.append(("Normal", f"{{\\pos({x},{y + gap(175)})}}{now.strftime('%d')}"))
    if settings.japanese:
        events.append(("Japanese", f"{{\\pos({x},{y + gap(225)})}}{greeting_jp}"))
    if settings.username:
        events.append(("Username", f"{{\\pos({x},{y + gap(265)})}}{settings.username}"))
    if settings.decorative_lines:
        events.extend((
            ("Lines", f"{{\\pos({x},{y + gap(325)})}}│"),
            ("Lines", f"{{\\pos({x},{y + gap(370)})}}│"),
        ))
    event_text = "\n".join(
        f"Dialogue: 0,0:00:00.00,9:59:59.00,{style},,0,0,0,,{text}"
        for style, text in events
    )
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Normal,Noto Sans,{sizes["normal"]},{primary},{primary},&H00000000,&H00000000,0,0,0,0,100,100,5,0,1,0,0,5,0,0,0,1
Style: Greeting,Noto Sans,{sizes["greeting"]},{primary},{primary},&H00000000,&H00000000,1,0,0,0,100,100,5,0,1,0,0,5,0,0,0,1
Style: Anurati,Anurati,{sizes["day"]},{accent},{accent},&H00000000,&H00000000,0,0,0,0,100,100,8,0,1,0,0,5,0,0,0,1
Style: Japanese,Noto Sans CJK JP,{sizes["japanese"]},{accent},{accent},&H00000000,&H00000000,0,0,0,0,100,100,2,0,1,0,0,5,0,0,0,1
Style: Username,Noto Sans CJK JP,{sizes["username"]},{secondary},{secondary},&H00000000,&H00000000,0,0,0,0,100,100,2,0,1,0,0,5,0,0,0,1
Style: Lines,Noto Sans,{sizes["lines"]},{secondary},{secondary},&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
{event_text}
"""


class HudManager:
    def __init__(self, cache_home: Path, config_home: Path):
        self.directory = Path(cache_home) / "hud"
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.palette_file = Path(config_home).parent / "waybar" / "panel-colors.css"
        self.settings = HudSettings()
        self._lock = threading.Lock()

    def configure(self, data: Any) -> None:
        self.settings = settings_from_config(data)

    def path(self, output: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "-", output)
        return self.directory / f"hud-{safe or 'all'}.ass"

    def render(self, output: str, width: int | None = None, height: int | None = None) -> Path | None:
        if not self.settings.enabled:
            return None
        if width is None or height is None:
            width, height = _monitor_size(output) or (1920, 1080)
        target = self.path(output)
        content = make_ass(width, height, self.settings, _palette(self.palette_file))
        temporary = target.with_suffix(".tmp")
        with self._lock:
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(target)
        return target
