"""Non-GTK facade used by the v2 GUI.

All potentially slow work is exposed as ordinary methods so the GTK layer can run
it in its worker pool.  This module never creates windows or starts playback while
being imported.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .discovery_download import DiscoveryDownloader
from .history import HistoryManager
from .ipc import EngineClient
from .library import Library
from .models import MediaType, PlaylistMode, Wallpaper
from .monitors import MonitorError, MonitorInfo, detect_monitors
from .paths import EnginePaths
from .playlists import PlaylistManager
from .recommendations import RecommendationEngine
from .theme_sync import ThemeSync


DEFAULT_LIBRARY_ROOTS = (
    Path.home() / "Pictures" / "Wallpapers" / "Live",
    Path.home() / "Pictures" / "wallpapers",
)


class GuiBackend:
    """One shared backend for Library, Favorites, Recent and Playlists pages."""

    def __init__(
        self,
        paths: EnginePaths | None = None,
        *,
        library: Library | None = None,
        client: EngineClient | None = None,
        monitor_detector=detect_monitors,
        theme_sync: ThemeSync | None = None,
        recommendations: RecommendationEngine | None = None,
        downloader: DiscoveryDownloader | None = None,
        library_roots: Iterable[Path] = DEFAULT_LIBRARY_ROOTS,
    ):
        self.paths = paths or EnginePaths.from_environment()
        self.library = library or Library(self.paths)
        self.client = client or EngineClient(self.paths)
        self.playlists = PlaylistManager(self.library)
        self.history = HistoryManager(self.library)
        self.monitor_detector = monitor_detector
        self.theme_sync = theme_sync or ThemeSync(self.paths)
        self.recommendations = recommendations or RecommendationEngine(self.paths)
        self.library_roots = tuple(Path(root).expanduser() for root in library_roots)
        self.downloader = downloader or DiscoveryDownloader(self.library_roots[0])

    def recommendation_data(self) -> dict:
        """Return one coherent snapshot for the Discover suggestions page."""
        settings = self.recommendations.settings()
        return {
            "settings": settings,
            "sources": self.recommendations.sources(),
            "items": self.recommendations.recommend(
                limit=settings["limit"],
                enabled_sources=settings["enabled_sources"],
            ),
        }

    def configure_recommendations(self, *, enabled_sources, limit: int) -> dict:
        return self.recommendations.configure(
            enabled_sources=enabled_sources, limit=limit
        )

    def recommendation_feedback(self, uri: str, value: int) -> None:
        self.recommendations.feedback(uri, value)

    def like_discovery_page(self, uri: str, title: str) -> None:
        self.recommendations.like(uri, title)

    def discovery_download_profile(self):
        return self.downloader.profile()

    def discovery_download_diagnostics(self):
        return self.downloader.diagnostics()

    def download_discovery_page(self, uri: str, title: str, height: int = 0,
                                *, firefox=False):
        result = self.downloader.download(
            uri, title, height, firefox=firefox
        )
        if result.path is not None and result.path.is_file():
            self.library.scan(self.library_roots)
        return result

    def refresh_library(self, *, scan: bool = True) -> list[Wallpaper]:
        if scan:
            self.library.scan(self.library_roots)
        return self.library.list()

    def ensure_thumbnail(self, wallpaper_id: int) -> Path:
        wallpaper = self._wallpaper(wallpaper_id)
        if wallpaper.thumbnail_path is not None and wallpaper.thumbnail_path.is_file():
            return wallpaper.thumbnail_path
        return self.library.rebuild_thumbnail(wallpaper_id)

    def search(
        self, query: str = "", *, kind: str = "all", favorites: bool = False
    ) -> list[Wallpaper]:
        media_type = None if kind == "all" else MediaType(kind)
        return self.library.search(
            query, media_type=media_type, favorites_only=favorites
        )

    def outputs(self) -> list[MonitorInfo]:
        try:
            return self.monitor_detector()
        except MonitorError:
            return []

    def apply(
        self, wallpaper_id: int, output: str, *,
        theme_mode: str = "off", performance_profile: str = "balanced",
    ) -> dict:
        wallpaper = self._wallpaper(wallpaper_id)
        result = self.client.play(output, str(wallpaper.path))
        self.history.start(wallpaper.id, output, "manual")
        theme = self.theme_sync.apply(
            wallpaper.path, mode=theme_mode, profile=performance_profile
        )
        return {**result, "theme_sync": theme.reason}

    def set_favorite(self, wallpaper_id: int, favorite: bool) -> Wallpaper:
        return self.library.set_favorite(wallpaper_id, favorite)

    def playback(self, action: str, output: str, value=None) -> dict:
        operations = {
            "pause": lambda: self.client.pause(output),
            "resume": lambda: self.client.resume(output),
            "restart": lambda: self.client.restart(output),
            "volume": lambda: self.client.set_volume(output, int(value)),
            "mute": lambda: self.client.set_mute(output, bool(value)),
            "speed": lambda: self.client.set_speed(output, float(value)),
            "loop": lambda: self.client.set_loop(output, bool(value)),
            "fit": lambda: self.client.set_fit(output, str(value)),
            "profile": lambda: self.client.set_performance_profile(output, str(value)),
            "color": lambda: self.client.set_color(output, dict(value)),
        }
        try:
            operation = operations[action]
        except KeyError as error:
            raise ValueError("unsupported GUI playback action") from error
        return operation()

    def create_playlist(
        self, name: str, mode: str = "sequential", interval: int | None = None
    ):
        return self.playlists.create(name, PlaylistMode(mode), interval)

    def add_to_playlist(self, playlist_id: int, wallpaper_id: int) -> None:
        self.playlists.add(playlist_id, wallpaper_id)

    def play_next(self, playlist_id: int, output: str, current_id: int | None = None):
        wallpaper = self.playlists.next(
            playlist_id, current_id=current_id, output=output
        )
        if wallpaper is None:
            return None
        result = self.client.play(output, str(wallpaper.path))
        self.history.start(wallpaper.id, output, "playlist")
        return wallpaper, result

    def _wallpaper(self, wallpaper_id: int) -> Wallpaper:
        wallpaper = self.library.get(wallpaper_id)
        if wallpaper is None or wallpaper.missing:
            raise KeyError(wallpaper_id)
        return wallpaper
