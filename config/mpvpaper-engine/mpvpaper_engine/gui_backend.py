"""Non-GTK facade used by the v2 GUI.

All potentially slow work is exposed as ordinary methods so the GTK layer can run
it in its worker pool.  This module never creates windows or starts playback while
being imported.
"""

from __future__ import annotations

from pathlib import Path
from copy import deepcopy
import subprocess
from typing import Iterable

from .discovery_download import DiscoveryDownloader
from .config import load_config, save_config
from .history import HistoryManager
from .ipc import EngineClient, EngineIPCError, EngineUnavailableError
from .library import Library
from .models import MediaType, OutputMode, PlaylistMode, Wallpaper
from .monitors import MonitorError, MonitorInfo, detect_monitors
from .hud_layers import HudLayerError, detect_layers, panel_rects
from .hud import font_status, effective_hud, merge_hud, normalized_hud, _palette, preview_settings
from .hud_scene import geometry as hud_geometry, logical_screen
import threading
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
        layer_detector=detect_layers,
        theme_sync: ThemeSync | None = None,
        recommendations: RecommendationEngine | None = None,
        downloader: DiscoveryDownloader | None = None,
        library_roots: Iterable[Path] = DEFAULT_LIBRARY_ROOTS,
    ):
        self.paths = paths or EnginePaths.from_environment()
        self.config = load_config(self.paths)
        self._hud_lock = threading.RLock()
        self._hud_revision = 0
        self.hud_live = False
        self.library = library or Library(self.paths)
        self.client = client or EngineClient(self.paths)
        self.playlists = PlaylistManager(self.library)
        self.history = HistoryManager(self.library)
        self.monitor_detector = monitor_detector
        self.layer_detector = layer_detector
        self.theme_sync = theme_sync or ThemeSync(self.paths)
        self.recommendations = recommendations or RecommendationEngine(self.paths)
        self.library_roots = tuple(Path(root).expanduser() for root in library_roots)
        self.downloader = downloader or DiscoveryDownloader(self.library_roots[0])

    def hud_settings(self) -> dict:
        hud = self.config.ui.get("hud", {})
        return deepcopy(hud) if isinstance(hud, dict) else {}

    def configure_hud(self, settings: dict) -> dict:
        with self._hud_lock:
            self._hud_revision += 1
            return self._save_hud(settings)

    def _save_hud(self, settings: dict) -> dict:
        if not isinstance(settings, dict):
            raise ValueError("les réglages HUD doivent être un objet JSON")
        candidate = load_config(self.paths) if self.paths.config_file.exists() else deepcopy(self.config)
        if candidate.load_error:
            raise ValueError(candidate.load_error)
        candidate.ui["hud"] = normalized_hud(merge_hud(candidate.ui.get("hud", {}), settings))
        save_config(candidate, self.paths)
        self.config = candidate
        try:
            result = self.client.configure_hud(self.config.ui["hud"])
            self.hud_live = isinstance(result, dict) and result.get("live", False) is True
        except (EngineIPCError, OSError, TimeoutError):
            # The configuration remains saved when the session service is offline.
            self.hud_live = False
        return self.hud_settings()

    def refresh_hud(self) -> dict:
        return self.client.refresh_hud("*")

    def reserve_hud_preview(self):
        with self._hud_lock:
            self._hud_revision += 1
            return self._hud_revision

    def preview_hud(self, output: str, settings: dict, revision=None) -> dict:
        if not isinstance(settings, dict):
            raise ValueError("les réglages HUD doivent être un objet JSON")
        with self._hud_lock:
            if revision is not None and revision != self._hud_revision:
                return {"previewed": [], "stale": True}
            return self.client.preview_hud(output, settings)

    def clear_hud_preview(self, output: str = "*") -> dict:
        with self._hud_lock:
            self._hud_revision += 1
            return self.client.clear_hud_preview(output)

    def commit_hud_preview(self, settings: dict, output: str = "*") -> dict:
        if not isinstance(settings, dict):
            raise ValueError("les réglages HUD doivent être un objet JSON")
        return self.configure_hud(settings if output == "*" else {"outputs": {output: settings}})

    def hud_editor_outputs(self) -> list[dict]:
        return [
            {"name": "*", "label": "Tous les écrans (*)"},
            *[
                {
                    "name": monitor.name,
                    "label": monitor.name,
                    "width": monitor.width,
                    "height": monitor.height,
                }
                for monitor in self.outputs()
            ],
        ]

    def hud_editor_state(self, output: str = "*") -> dict:
        monitors = self.outputs()
        monitor = self._hud_monitor(monitors, output)
        settings = self._hud_effective_settings(output)
        if monitor is None or not monitor.width or not monitor.height:
            return {
                "output": output, "settings": settings, "monitor": None,
                "layers": [], "safe_area": None, "ratio": None,
            }
        screen = logical_screen(monitor)
        layers = self._hud_layers(monitor.name)
        panels = panel_rects(layers, monitor.name)
        render_settings = normalized_hud(effective_hud(self.hud_settings(), monitor.name))
        result = self._hud_geometry(output, render_settings, monitor, screen, panels)
        result["settings"] = settings
        return result

    def hud_editor_preview_data(self, output: str, settings: dict) -> dict:
        if not isinstance(settings, dict):
            raise ValueError("les réglages HUD doivent être un objet JSON")
        monitors = self.outputs()
        monitor = self._hud_monitor(monitors, output)
        if monitor is None or not monitor.width or not monitor.height:
            return self.hud_editor_state(output)
        screen = logical_screen(monitor)
        panels = panel_rects(self._hud_layers(monitor.name), monitor.name)
        render_settings = preview_settings(self.hud_settings(), monitor.name, {output: settings})
        return self._hud_geometry(output, render_settings, monitor, screen, panels)

    def _hud_monitor(self, monitors: list[MonitorInfo], output: str):
        if output != "*":
            return next((item for item in monitors if item.name == output), None)
        return next((item for item in monitors if item.focused), monitors[0] if monitors else None)

    def _hud_effective_settings(self, output: str) -> dict:
        return normalized_hud(effective_hud(self.hud_settings(), output))

    def _hud_layers(self, monitor: str):
        try:
            return self.layer_detector()
        except HudLayerError:
            return []

    def _hud_geometry(self, output, settings, monitor, screen, panels):
        settings = normalized_hud(settings)
        layout = hud_geometry(settings, screen, panels)
        area = layout["safe_area"]
        fonts = font_status()

        def relative(rect):
            return {
                "x": rect.x - screen.x, "y": rect.y - screen.y,
                "width": rect.width, "height": rect.height,
            }
        return {
            "output": output,
            "settings": deepcopy(settings),
            "render_settings": deepcopy(settings),
            "palette": _palette(self.paths.config_home.parent / "waybar" / "panel-colors.css"),
            "monitor": {
                "name": monitor.name, "x": monitor.x or 0, "y": monitor.y or 0,
                "width": screen.width, "height": screen.height,
                "scale": monitor.scale, "focused": monitor.focused,
            },
            "ratio": screen.width / screen.height,
            "layers": [relative(rect) for rect in panels],
            "safe_area": relative(area),
            "hud_rect": relative(layout["rect"]),
            "positioning": {
                "resolved": layout["resolved"],
                "collision": layout["collision"],
                "snapped": layout["snapped"],
                "limited": layout["limited"],
            },
            "fonts": fonts,
        }

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
        targets = [output]
        if output == "*":
            targets = [item.name for item in self.outputs()]
            if not targets:
                raise ValueError("aucun écran connecté")
        try:
            result = self.client.play(output, str(wallpaper.path))
        except EngineUnavailableError:
            subprocess.run(
                ["systemctl", "--user", "start", "mpvpaper-engine.service"],
                check=True,
            )
            result = self.client.play(output, str(wallpaper.path))
        self._save_wallpaper_selection(output, wallpaper.path, performance_profile)
        for target in targets:
            self.history.start(wallpaper.id, target, "manual")
        theme = self.theme_sync.apply(
            wallpaper.path, mode=theme_mode, profile=performance_profile
        )
        try:
            for target in targets:
                self.client.refresh_hud(target)
        except (EngineIPCError, OSError, TimeoutError):
            pass
        return {**result, "theme_sync": theme.reason}

    def _save_wallpaper_selection(
        self, output: str, wallpaper: Path, performance_profile: str,
    ) -> None:
        profile = {
            "wallpaper": str(wallpaper),
            "performance_profile": performance_profile,
            "autostart": True,
        }
        self.config.outputs[output] = {
            **self.config.outputs.get(output, {}),
            **profile,
        }
        self.config.selected_output = output
        self.config.selected_profile = {
            **self.config.selected_profile,
            **profile,
        }
        if output == "*":
            self.config.mode = OutputMode.SAME
        else:
            self.config.mode = OutputMode.INDEPENDENT
        save_config(self.config, self.paths)

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
