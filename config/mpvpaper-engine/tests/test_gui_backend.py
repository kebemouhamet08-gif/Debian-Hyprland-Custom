from pathlib import Path
import json
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
from mpvpaper_engine.monitors import MonitorInfo  # noqa: E402
from mpvpaper_engine.hud_layers import HudLayer  # noqa: E402
from mpvpaper_engine.hud_positioning import Rect  # noqa: E402
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
        saved = json.loads(self.paths.config_file.read_text())
        self.assertEqual(
            saved["outputs"]["DP-1"]["wallpaper"], str(self.wallpaper.path)
        )
        self.assertTrue(saved["outputs"]["DP-1"]["autostart"])

    def test_live_controls_are_dispatched_to_single_backend(self):
        self.backend.playback("volume", "DP-1", 33)
        self.backend.playback("profile", "DP-1", "eco")
        self.client.set_volume.assert_called_once_with("DP-1", 33)
        self.client.set_performance_profile.assert_called_once_with("DP-1", "eco")

    def test_hud_settings_are_saved_and_sent_to_engine(self):
        settings = {
            "enabled": False,
            "position": {"x": 0.25, "y": 0.4},
            "scale": 1.2,
            "opacity": 0.8,
            "username": "テスト",
            "elements": {"time": False},
        }

        self.backend.configure_hud(settings)

        saved = self.backend.hud_settings()
        for key, value in settings.items():
            if key == "elements":
                self.assertFalse(saved[key]["time"])
            else:
                self.assertEqual(saved[key], value)
        self.client.configure_hud.assert_called_once_with(saved)
        self.assertEqual(
            json.loads(self.paths.config_file.read_text())["ui"]["hud"], saved
        )

    def test_hud_preview_facade_does_not_persist_and_commit_does(self):
        settings = {"enabled": True, "position": {"x": 0.7, "y": 0.6}}
        self.backend.preview_hud("DP-1", settings)
        self.client.preview_hud.assert_called_once_with("DP-1", settings)
        self.assertFalse(self.paths.config_file.exists())

        self.backend.clear_hud_preview("DP-1")
        self.client.clear_hud_preview.assert_called_once_with("DP-1")
        self.backend.commit_hud_preview(settings)
        self.client.configure_hud.assert_called_once_with(self.backend.hud_settings())
        self.assertTrue(self.paths.config_file.exists())

    def test_hud_partial_edit_keeps_colors_and_other_screen_settings(self):
        self.backend.configure_hud({"colors": {"mode": "custom", "custom": {"accent": "#123456"}},
                                    "outputs": {"DP-2": {"scale": 1.7}}})
        self.backend.configure_hud({"position": {"x": .73}})
        saved = self.backend.hud_settings()
        self.assertEqual(saved["colors"]["custom"]["accent"], "#123456")
        self.assertEqual(saved["outputs"]["DP-2"]["scale"], 1.7)
        self.assertEqual(saved["position"]["x"], .73)
        self.assertEqual(saved["position"]["y"], .3)

    def test_stale_preview_cannot_override_apply_or_cancel(self):
        revision = self.backend.reserve_hud_preview()
        self.backend.commit_hud_preview({"position": {"x": .8}})
        response = self.backend.preview_hud("*", {"position": {"x": .1}}, revision)
        self.assertTrue(response["stale"])
        self.client.preview_hud.assert_not_called()
        revision = self.backend.reserve_hud_preview()
        self.backend.clear_hud_preview("*")
        self.assertTrue(self.backend.preview_hud("*", {}, revision)["stale"])
        self.client.preview_hud.assert_not_called()

    def test_hud_editor_and_renderer_share_scaled_geometry(self):
        from mpvpaper_engine.hud_scene import geometry, logical_screen
        monitor = MonitorInfo("DP-1", 3840, 2160, x=-1920, y=0, scale=2)
        self.backend.monitor_detector = lambda: [monitor]
        self.backend.layer_detector = lambda: []
        settings = {"enabled": True, "position": {"x": .4, "y": .6},
                    "anchor": "bottom-right", "scale": .75, "snap": False, "avoid_layers": False}
        state = self.backend.hud_editor_preview_data("DP-1", settings)
        expected = geometry(settings, logical_screen(monitor))["rect"]
        self.assertEqual(state["monitor"]["width"], 1920)
        self.assertEqual(state["hud_rect"], {"x": expected.x + 1920, "y": expected.y,
                                             "width": expected.width, "height": expected.height})

    def test_hud_save_preserves_wallpaper_changed_by_another_client(self):
        from mpvpaper_engine.config import load_config, save_config
        self.backend.configure_hud({"scale": 1.1})
        external = load_config(self.paths)
        external.outputs["DP-9"] = {"wallpaper": "/new/wallpaper.png"}
        save_config(external, self.paths)
        self.backend.configure_hud({"opacity": .7})
        saved = load_config(self.paths)
        self.assertEqual(saved.outputs["DP-9"]["wallpaper"], "/new/wallpaper.png")

    def test_hud_editor_state_exposes_geometry_layers_and_safe_area(self):
        monitor = MonitorInfo("eDP-1", 1920, 1080, x=0, y=0, focused=True)
        layer = HudLayer("eDP-1", "waybar", Rect(0, 0, 1920, 36), "top")
        backend = GuiBackend(
            self.paths, library=self.library, client=self.client,
            monitor_detector=lambda: [monitor], layer_detector=lambda: [layer],
            library_roots=(self.root,), theme_sync=self.theme_sync,
        )
        state = backend.hud_editor_state("eDP-1")
        self.assertEqual(state["monitor"]["width"], 1920)
        self.assertEqual(state["layers"][0]["height"], 36)
        self.assertEqual(state["safe_area"]["y"], 60)
        self.assertAlmostEqual(state["ratio"], 1920 / 1080)

    def test_hud_editor_wildcard_uses_focused_monitor_and_handles_no_monitors(self):
        monitor = MonitorInfo("HDMI-A-1", 2560, 1440, focused=True)
        backend = GuiBackend(
            self.paths, library=self.library, client=self.client,
            monitor_detector=lambda: [monitor], layer_detector=lambda: [],
            library_roots=(self.root,), theme_sync=self.theme_sync,
        )
        self.assertEqual(backend.hud_editor_state("*")["monitor"]["name"], "HDMI-A-1")
        empty = GuiBackend(
            self.paths, library=self.library, client=self.client,
            monitor_detector=lambda: [], layer_detector=lambda: [],
            library_roots=(self.root,), theme_sync=self.theme_sync,
        )
        self.assertIsNone(empty.hud_editor_state("*")["monitor"])

    def test_hud_editor_apply_persists_selected_output_override(self):
        settings = {"enabled": True, "position": {"x": 0.8, "y": 0.6}}
        self.backend.commit_hud_preview(settings, "HDMI-A-1")
        saved = json.loads(self.paths.config_file.read_text())
        self.assertEqual(saved["ui"]["hud"]["outputs"]["HDMI-A-1"], settings)
        self.client.configure_hud.assert_called_once()

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
