from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.gui_backend import GuiBackend  # noqa: E402
from mpvpaper_engine.library import Library  # noqa: E402
from mpvpaper_engine.metadata import MediaMetadata  # noqa: E402
from mpvpaper_engine.models import MediaType  # noqa: E402
from mpvpaper_engine.paths import EnginePaths  # noqa: E402


def paths(root):
    root = Path(root)
    return EnginePaths.from_environment({
        "HOME": str(root), "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"), "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_RUNTIME_DIR": str(root / "runtime"),
    })


class GuiBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "wallpapers"
        self.root.mkdir()
        self.paths = paths(self.temp.name)
        probe = lambda _path: MediaMetadata(
            MediaType.VIDEO, 12, 1920, 1080, 30, "h264", None, 1000
        )
        self.library = Library(self.paths, probe=probe)
        self.client = mock.Mock()
        self.theme_sync = mock.Mock()
        self.theme_sync.apply.return_value.reason = "theme sync is off"
        self.backend = GuiBackend(
            self.paths, library=self.library, client=self.client,
            monitor_detector=lambda: [], library_roots=(self.root,),
            theme_sync=self.theme_sync,
        )
        media = self.root / "night.mp4"
        media.write_bytes(b"video")
        self.wallpaper = self.library.import_file(media)

    def tearDown(self):
        self.temp.cleanup()

    def test_search_and_persistent_favorite_share_library(self):
        self.assertEqual(self.backend.search("night")[0].id, self.wallpaper.id)
        self.backend.set_favorite(self.wallpaper.id, True)
        self.assertEqual(self.backend.search(favorites=True)[0].id, self.wallpaper.id)

    def test_apply_uses_engine_and_records_history(self):
        self.client.play.return_value = {"strategy": "loadfile"}
        result = self.backend.apply(self.wallpaper.id, "DP-1")
        self.assertEqual(result["strategy"], "loadfile")
        self.client.play.assert_called_once_with("DP-1", str(self.wallpaper.path))
        self.theme_sync.apply.assert_called_once_with(
            self.wallpaper.path, mode="off", profile="balanced"
        )
        self.assertEqual(self.backend.history.list(output="DP-1")[0].wallpaper_id,
                         self.wallpaper.id)

    def test_live_controls_are_dispatched_to_single_backend(self):
        self.backend.playback("volume", "DP-1", 33)
        self.backend.playback("profile", "DP-1", "eco")
        self.client.set_volume.assert_called_once_with("DP-1", 33)
        self.client.set_performance_profile.assert_called_once_with("DP-1", "eco")

    def test_pasted_url_is_sent_to_discovery_downloader(self):
        downloader = mock.Mock()
        downloader.download.return_value = mock.Mock(path=None)
        backend = GuiBackend(
            self.paths, library=self.library, client=self.client,
            monitor_detector=lambda: [], library_roots=(self.root,),
            theme_sync=self.theme_sync, downloader=downloader,
        )

        backend.download_discovery_page(
            "https://www.youtube.com/watch?v=example", "wallpaper", 1080
        )

        downloader.download.assert_called_once_with(
            "https://www.youtube.com/watch?v=example", "wallpaper", 1080,
            firefox=False,
        )

    def test_playlist_next_is_functional(self):
        playlist = self.backend.create_playlist("Night")
        self.backend.add_to_playlist(playlist.id, self.wallpaper.id)
        selected, _result = self.backend.play_next(playlist.id, "DP-1")
        self.assertEqual(selected.id, self.wallpaper.id)
        self.assertEqual(self.backend.history.list()[0].reason, "playlist")


if __name__ == "__main__":
    unittest.main()
