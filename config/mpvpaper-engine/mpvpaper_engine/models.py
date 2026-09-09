"""Side-effect-free data models shared by every MPVpaper Engine client."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StringEnum(str, Enum):
    """Enum whose members serialize naturally as string values."""


class MediaType(StringEnum):
    IMAGE = "image"
    VIDEO = "video"


class PlaybackStatus(StringEnum):
    STOPPED = "stopped"
    LOADING = "loading"
    PLAYING = "playing"
    PAUSED = "paused"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


class OutputMode(StringEnum):
    SAME = "same"
    INDEPENDENT = "independent"
    SYNC = "sync"
    DISABLED = "disabled"


class PerformanceMode(StringEnum):
    AUTO = "auto"
    ECO = "eco"
    BALANCED = "balanced"
    QUALITY = "quality"


class PlaylistMode(StringEnum):
    SEQUENTIAL = "sequential"
    SHUFFLE = "shuffle"
    SMART = "smart"


class DownloadState(StringEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnimatedPreview(StringEnum):
    OFF = "off"
    SELECTION = "selection"
    HOVER = "hover"


@dataclass(slots=True)
class Wallpaper:
    id: int
    path: Path
    title: str
    media_type: MediaType
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    bitrate: int | None = None
    file_size: int = 0
    mtime_ns: int = 0
    fingerprint: str = ""
    content_signature: str | None = None
    thumbnail_path: Path | None = None
    source: str = "local"
    source_url: str | None = None
    favorite: bool = False
    date_added: datetime = field(default_factory=utc_now)
    last_used: datetime | None = None
    usage_count: int = 0
    missing: bool = False


@dataclass(slots=True)
class OutputProfile:
    output: str
    enabled: bool = True
    mode: OutputMode = OutputMode.INDEPENDENT
    sync_group: str | None = None
    wallpaper_id: int | None = None
    playlist_id: int | None = None
    volume: int = 0
    muted: bool = True
    speed: float = 1.0
    loop: bool = True
    fit_mode: str = "cover"
    performance_profile: PerformanceMode = PerformanceMode.AUTO
    color_profile: str = "Original"
    theme_sync: str = "off"
    autostart: bool = True


@dataclass(slots=True)
class PlaybackState:
    output: str
    status: PlaybackStatus = PlaybackStatus.STOPPED
    wallpaper_id: int | None = None
    path: Path | None = None
    position: float | None = None
    duration: float | None = None
    volume: int | None = None
    muted: bool | None = None
    speed: float | None = None
    playlist_id: int | None = None
    performance_profile: PerformanceMode = PerformanceMode.AUTO
    color_profile: str = "Original"
    last_error: str | None = None
    service_pid: int | None = None
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class ColorProfile:
    name: str = "Original"
    brightness: int = 0
    contrast: int = 0
    gamma: int = 0
    saturation: int = 0
    hue: int = 0
    temperature: int = 6500
    red_balance: int = 0
    green_balance: int = 0
    blue_balance: int = 0


@dataclass(slots=True)
class PerformanceProfile:
    name: PerformanceMode = PerformanceMode.AUTO
    hwdec: str = "auto-safe"
    fps_limit: int | None = None
    render_height: int | None = None
    pause_on_fullscreen: bool = True
    pause_on_lock: bool = True
    pause_on_dpms: bool = True
    animated_preview: AnimatedPreview = AnimatedPreview.SELECTION
    theme_analysis_frames: int = 4


@dataclass(slots=True)
class Playlist:
    id: int
    name: str
    mode: PlaylistMode = PlaylistMode.SEQUENTIAL
    interval_seconds: int | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class PlaylistItem:
    playlist_id: int
    wallpaper_id: int
    position: int
    weight: float = 1.0


@dataclass(slots=True)
class HistoryEntry:
    id: int
    wallpaper_id: int | None
    output: str
    started_at: datetime
    ended_at: datetime | None = None
    reason: str = "manual"


@dataclass(slots=True)
class DownloadJob:
    id: str
    source: str
    url: str
    destination: Path | None = None
    progress: float = 0.0
    speed_bytes: float | None = None
    eta_seconds: float | None = None
    state: DownloadState = DownloadState.QUEUED
    error: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
