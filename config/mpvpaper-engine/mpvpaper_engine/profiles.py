"""Performance profiles and explainable AUTO selection."""

from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
import subprocess
from typing import Callable

from .models import AnimatedPreview, PerformanceMode


@dataclass(frozen=True, slots=True)
class HardwareContext:
    cpu_count: int
    ram_gib: float
    total_output_pixels: int
    gpu_class: str = "unknown"
    on_battery: bool = False
    power_saver: bool = False
    media_height: int | None = None
    media_fps: float | None = None
    available_hwdec: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EffectivePerformanceSettings:
    requested: PerformanceMode
    effective: PerformanceMode
    hwdec: str
    fps_limit: int | None
    render_height: int | None
    pause_on_fullscreen: bool
    pause_on_lock: bool
    pause_on_dpms: bool
    animated_preview: AnimatedPreview
    theme_analysis_frames: int
    reason: str


PROFILES = {
    PerformanceMode.ECO: EffectivePerformanceSettings(
        PerformanceMode.ECO, PerformanceMode.ECO, "auto-safe", 24, 720,
        True, True, True, AnimatedPreview.OFF, 2, "ECO selected",
    ),
    PerformanceMode.BALANCED: EffectivePerformanceSettings(
        PerformanceMode.BALANCED, PerformanceMode.BALANCED, "auto-safe", 30, 1080,
        True, True, True, AnimatedPreview.SELECTION, 4, "BALANCED selected",
    ),
    PerformanceMode.QUALITY: EffectivePerformanceSettings(
        PerformanceMode.QUALITY, PerformanceMode.QUALITY, "auto-safe", None, None,
        False, True, True, AnimatedPreview.SELECTION, 4, "QUALITY selected",
    ),
}


def detect_hwdec(runner: Callable = subprocess.run) -> tuple[str, ...]:
    try:
        result = runner(
            ["mpv", "--no-config", "--hwdec=help"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()
    if result.returncode != 0:
        return ()
    known = ("vaapi", "nvdec", "vdpau", "vulkan", "drm", "cuda")
    lowered = result.stdout.casefold()
    return tuple(name for name in known if name in lowered)


def detect_hardware_context(
    *,
    total_output_pixels: int = 0,
    gpu_class: str = "unknown",
    media_height: int | None = None,
    media_fps: float | None = None,
    runner: Callable = subprocess.run,
) -> HardwareContext:
    ram_gib = 0.0
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                ram_gib = int(line.split()[1]) / (1024 * 1024)
                break
    except (OSError, ValueError, IndexError):
        pass
    supplies = Path("/sys/class/power_supply")
    batteries = list(supplies.glob("BAT*")) if supplies.is_dir() else []
    mains = list(supplies.glob("AC*/online")) + list(supplies.glob("ADP*/online"))
    online = any(path.read_text().strip() == "1" for path in mains if path.is_file())
    on_battery = bool(batteries) and not online
    return HardwareContext(
        cpu_count=os.cpu_count() or 1,
        ram_gib=ram_gib,
        total_output_pixels=max(0, int(total_output_pixels)),
        gpu_class=gpu_class if gpu_class in {"integrated", "discrete", "unknown"} else "unknown",
        on_battery=on_battery,
        media_height=media_height,
        media_fps=media_fps,
        available_hwdec=detect_hwdec(runner),
    )


def select_auto(context: HardwareContext) -> tuple[PerformanceMode, str]:
    if context.power_saver or context.on_battery:
        return PerformanceMode.ECO, "battery or power-saver active"
    if context.cpu_count <= 2 or context.ram_gib < 4:
        return PerformanceMode.ECO, "limited CPU or RAM"
    if context.gpu_class == "integrated" and context.total_output_pixels > 4_000_000:
        return PerformanceMode.ECO, "integrated GPU driving a high pixel count"
    if (
        context.gpu_class == "discrete"
        and context.cpu_count >= 6
        and context.ram_gib >= 12
        and bool(context.available_hwdec)
    ):
        return PerformanceMode.QUALITY, "discrete GPU and sufficient system resources"
    return PerformanceMode.BALANCED, "balanced default for detected resources"


def effective_settings(
    requested: PerformanceMode | str,
    context: HardwareContext | None = None,
) -> EffectivePerformanceSettings:
    try:
        mode = requested if isinstance(requested, PerformanceMode) else PerformanceMode(requested)
    except ValueError as error:
        raise ValueError("invalid performance profile") from error
    if mode != PerformanceMode.AUTO:
        return PROFILES[mode]
    if context is None:
        context = HardwareContext(4, 8, 2_073_600)
    selected, reason = select_auto(context)
    settings = PROFILES[selected]
    fps_limit = settings.fps_limit
    if fps_limit is not None and context.media_fps is not None:
        fps_limit = max(1, min(fps_limit, round(context.media_fps)))
    render_height = settings.render_height
    if render_height is not None and context.media_height is not None:
        render_height = min(render_height, context.media_height)
    return replace(
        settings, requested=PerformanceMode.AUTO,
        fps_limit=fps_limit, render_height=render_height, reason=reason,
    )


def mpv_option_fragments(settings: EffectivePerformanceSettings) -> list[str]:
    options = [f"hwdec={settings.hwdec}"] if settings.hwdec else []
    if settings.fps_limit is not None:
        options.append(f"vf-add=fps=fps={settings.fps_limit}")
    if settings.render_height is not None:
        options.append(
            f"vf-add=scale=-2:{settings.render_height}:force_original_aspect_ratio=decrease"
        )
    return options
