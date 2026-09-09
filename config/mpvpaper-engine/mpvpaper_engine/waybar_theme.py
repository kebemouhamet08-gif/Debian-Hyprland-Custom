"""Atomic Waybar palette generation shared by wallpaper integrations."""

from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile


def _colors(path: Path) -> dict[str, str]:
    values = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        match = re.match(
            r"\s*@define-color\s+(color13|foreground|background|color8)\s+"
            r"(#[0-9a-fA-F]{6});", line,
        )
        if match:
            values[match.group(1)] = match.group(2)
    return values


def _rgb(value: str) -> str:
    value = value.lstrip("#")
    return f"{int(value[0:2], 16)}, {int(value[2:4], 16)}, {int(value[4:6], 16)}"


def _mix(base: str, tint: str, percent: int = 18) -> str:
    base = base.lstrip("#")
    tint = tint.lstrip("#")
    values = [
        (int(base[index:index + 2], 16) * (100 - percent)
         + int(tint[index:index + 2], 16) * percent) // 100
        for index in (0, 2, 4)
    ]
    return ", ".join(str(value) for value in values)


def write_panel_colors(
    waybar_dir: Path,
    *,
    palette: dict[str, str] | None = None,
    opacity: str = "0.86",
) -> bool:
    """Write panel-colors.css atomically; return whether content changed."""
    waybar_dir = Path(waybar_dir)
    wallust_file = waybar_dir / "wallust" / "colors-waybar.css"
    current = _colors(wallust_file)
    palette = palette or {}
    accent = current.get("color13") or palette.get("accent", "#d4cdd8")
    text = current.get("foreground") or palette.get("foreground", "#f3edf2")
    background = current.get("background") or palette.get("background", "#0e0f16")
    muted = current.get("color8") or palette.get("muted", "#b8aeb8")
    content = (
        "/* Generated from the current wallpaper by MPVpaper Engine. */\n"
        f"@define-color glass rgba({_mix(background, accent)}, {opacity});\n"
        f"@define-color glass_hover rgba({_rgb(accent)}, 0.30);\n"
        f"@define-color accent {accent};\n"
        f"@define-color accent_soft rgba({_rgb(accent)}, 0.42);\n"
        f"@define-color text {text};\n"
        f"@define-color muted {muted};\n"
    )
    target = waybar_dir / "panel-colors.css"
    try:
        if target.is_file() and target.read_text(encoding="utf-8") == content:
            return False
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent,
            prefix=".panel-colors.", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, target)
        return True
    finally:
        if "temporary" in locals() and temporary.exists():
            temporary.unlink()
