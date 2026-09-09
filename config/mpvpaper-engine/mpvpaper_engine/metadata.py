"""Media metadata, bounded fingerprints and lazy static thumbnails."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Callable

from .models import MediaType


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
HASH_CHUNK_SIZE = 1024 * 1024
PROBE_TIMEOUT = 12.0
THUMBNAIL_TIMEOUT = 30.0


class MetadataError(RuntimeError):
    pass


@dataclass(slots=True)
class MediaMetadata:
    media_type: MediaType
    duration: float | None
    width: int | None
    height: int | None
    fps: float | None
    video_codec: str | None
    audio_codec: str | None
    bitrate: int | None


def media_type_for_path(path: Path) -> MediaType:
    suffix = Path(path).suffix.casefold()
    if suffix in IMAGE_EXTENSIONS:
        return MediaType.IMAGE
    if suffix in VIDEO_EXTENSIONS:
        return MediaType.VIDEO
    raise ValueError("unsupported media type")


def _number(value, converter=float):
    try:
        return converter(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _fps(value: Any) -> float | None:
    if not isinstance(value, str):
        return _number(value)
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        top, bottom = _number(numerator), _number(denominator)
        return top / bottom if top is not None and bottom not in {None, 0} else None
    return _number(value)


def probe_media(path: Path, runner: Callable = subprocess.run) -> MediaMetadata:
    path = Path(path).expanduser().resolve()
    media_type = media_type_for_path(path)
    if not path.is_file():
        raise MetadataError(f"media does not exist: {path}")
    command = [
        "ffprobe", "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(path),
    ]
    try:
        result = runner(
            command, capture_output=True, text=True,
            timeout=PROBE_TIMEOUT, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MetadataError(str(error)) from error
    if result.returncode != 0:
        raise MetadataError(result.stderr.strip() or "ffprobe failed")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise MetadataError("ffprobe returned invalid JSON") from error
    streams = data.get("streams") if isinstance(data.get("streams"), list) else []
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
    format_data = data.get("format") if isinstance(data.get("format"), dict) else {}
    duration = _number(format_data.get("duration"))
    if media_type == MediaType.IMAGE:
        duration = None
    bitrate = _number(format_data.get("bit_rate"), int)
    return MediaMetadata(
        media_type=media_type,
        duration=duration,
        width=_number(video.get("width"), int),
        height=_number(video.get("height"), int),
        fps=_fps(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        video_codec=video.get("codec_name") if isinstance(video.get("codec_name"), str) else None,
        audio_codec=audio.get("codec_name") if isinstance(audio.get("codec_name"), str) else None,
        bitrate=bitrate,
    )


def scan_fingerprint(path: Path) -> str:
    path = Path(path).expanduser().resolve()
    info = path.stat()
    payload = f"{path}\0{info.st_size}\0{info.st_mtime_ns}".encode()
    return hashlib.sha256(payload).hexdigest()


def content_signature(path: Path, chunk_size: int = HASH_CHUNK_SIZE) -> str:
    path = Path(path).expanduser().resolve()
    info = path.stat()
    digest = hashlib.sha256()
    digest.update(str(info.st_size).encode() + b"\0")
    with path.open("rb") as stream:
        digest.update(stream.read(chunk_size))
        if info.st_size > chunk_size:
            stream.seek(max(0, info.st_size - chunk_size))
            digest.update(stream.read(chunk_size))
    return f"{info.st_size}:{digest.hexdigest()}"


def thumbnail_destination(path: Path, thumbnail_dir: Path) -> Path:
    key = hashlib.sha256(str(Path(path).expanduser().resolve()).encode()).hexdigest()
    return Path(thumbnail_dir) / f"{key}.jpg"


def generate_thumbnail(
    path: Path,
    thumbnail_dir: Path,
    runner: Callable = subprocess.run,
) -> Path:
    path = Path(path).expanduser().resolve()
    media_type_for_path(path)
    destination = thumbnail_destination(path, thumbnail_dir)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.stem}.new.jpg")
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        *( ["-ss", "2"] if path.suffix.casefold() in VIDEO_EXTENSIONS else [] ),
        "-i", str(path), "-frames:v", "1",
        "-vf", "scale=640:360:force_original_aspect_ratio=decrease",
        str(temporary),
    ]
    try:
        result = runner(
            command, capture_output=True, text=True,
            timeout=THUMBNAIL_TIMEOUT, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        temporary.unlink(missing_ok=True)
        raise MetadataError(str(error)) from error
    if result.returncode != 0 or not temporary.is_file() or not temporary.stat().st_size:
        temporary.unlink(missing_ok=True)
        raise MetadataError(result.stderr.strip() or "thumbnail generation failed")
    temporary.replace(destination)
    destination.chmod(0o600)
    return destination
