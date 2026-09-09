"""XDG-aware paths used by MPVpaper Engine.

This module only describes paths. Importing it never creates directories.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
import os
from pathlib import Path
import re


APPLICATION_DIRECTORY = "mpvpaper-engine"


@dataclass(frozen=True, slots=True)
class EnginePaths:
    """All persistent, cached and runtime locations for one engine session."""

    config_home: Path
    data_home: Path
    cache_home: Path
    runtime_home: Path

    config_file: Path
    library_db: Path
    recommendations_db: Path

    thumbnail_dir: Path
    suggestion_cache_dir: Path
    temp_dir: Path
    palette_dir: Path
    log_dir: Path

    state_file: Path
    engine_socket: Path
    mpv_socket_dir: Path
    lock_dir: Path

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        home: Path | None = None,
        uid: int | None = None,
    ) -> "EnginePaths":
        """Build paths from XDG variables without touching the filesystem."""

        values = os.environ if environ is None else environ
        user_home = Path(home) if home is not None else Path(
            values.get("HOME") or Path.home()
        )
        config_root = Path(values.get("XDG_CONFIG_HOME") or user_home / ".config")
        data_root = Path(values.get("XDG_DATA_HOME") or user_home / ".local" / "share")
        cache_root = Path(values.get("XDG_CACHE_HOME") or user_home / ".cache")
        runtime_value = values.get("XDG_RUNTIME_DIR")
        runtime_root = (
            Path(runtime_value)
            if runtime_value
            else Path("/tmp") / f"mpvpaper-engine-{os.getuid() if uid is None else uid}"
        )

        config_home = config_root / APPLICATION_DIRECTORY
        data_home = data_root / APPLICATION_DIRECTORY
        cache_home = cache_root / APPLICATION_DIRECTORY
        runtime_home = runtime_root / APPLICATION_DIRECTORY
        mpv_socket_dir = runtime_home / "mpv"

        return cls(
            config_home=config_home,
            data_home=data_home,
            cache_home=cache_home,
            runtime_home=runtime_home,
            config_file=config_home / "config.json",
            library_db=data_home / "library.db",
            recommendations_db=data_home / "recommendations.db",
            thumbnail_dir=cache_home / "thumbnails",
            suggestion_cache_dir=cache_home / "suggestions",
            temp_dir=cache_home / "temp",
            palette_dir=cache_home / "palettes",
            log_dir=cache_home / "logs",
            state_file=runtime_home / "state.json",
            engine_socket=runtime_home / "engine.sock",
            mpv_socket_dir=mpv_socket_dir,
            lock_dir=runtime_home / "locks",
        )

    def mpv_socket(self, output: str) -> Path:
        """Return the deterministic MPV IPC socket for a Hyprland output."""

        suffix = "all" if output == "*" else re.sub(r"[^A-Za-z0-9_.-]", "-", output)
        if not suffix or suffix in {".", ".."}:
            raise ValueError("invalid output name")
        return self.mpv_socket_dir / f"{suffix}.sock"
