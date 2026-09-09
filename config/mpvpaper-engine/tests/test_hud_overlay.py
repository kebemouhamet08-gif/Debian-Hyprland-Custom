from pathlib import Path
import sys
import tempfile
import unittest
import json
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1]))
from mpvpaper_engine.hud_overlay import DesktopHud, wayland_environment
from mpvpaper_engine.paths import EnginePaths
from mpvpaper_engine.config import normalize_v2_config
from mpvpaper_engine.playback import PlaybackController


class HudOverlayTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.paths = EnginePaths.from_environment({"HOME": temporary.name,
                                                  "XDG_RUNTIME_DIR": temporary.name + "/run"})
        self.process = mock.Mock()
        self.process.poll.return_value = None
        self.popen = mock.Mock(return_value=self.process)
        self.overlay = DesktopHud(self.paths, popen=self.popen)
        self.addCleanup(self.overlay.close)

    def test_update_reuses_one_process_without_wallpaper(self):
        self.assertFalse(self.overlay.update({"enabled": True}))
        self.overlay.start({"enabled": True})
        self.overlay.update({"enabled": False})
        self.assertEqual(self.popen.call_count, 1)
        self.assertEqual(json.loads(self.overlay.state_file.read_text())["settings"], {"enabled": False})
        self.assertIn("mpvpaper_engine.hud_window", self.popen.call_args.args[0])
        self.assertEqual(self.overlay.state_file.stat().st_mode & 0o777, 0o600)

    def test_systemd_start_recovers_wayland_socket(self):
        runtime = self.paths.runtime_home
        runtime.mkdir(parents=True, exist_ok=True)
        socket_path = runtime / "wayland-1"
        with mock.patch.object(Path, "glob", return_value=[socket_path]), \
                mock.patch.object(Path, "is_socket", return_value=True):
            environment = wayland_environment({"XDG_RUNTIME_DIR": str(runtime)})
        self.assertEqual(environment["WAYLAND_DISPLAY"], "wayland-1")

    def test_existing_wayland_display_is_preserved(self):
        environment = wayland_environment({
            "XDG_RUNTIME_DIR": str(self.paths.runtime_home),
            "WAYLAND_DISPLAY": "wayland-custom",
        })
        self.assertEqual(environment["WAYLAND_DISPLAY"], "wayland-custom")

    def test_stop_wallpaper_never_stops_or_reconfigures_hud(self):
        systemd = mock.Mock()
        controller = PlaybackController(normalize_v2_config({"schema_version": 2}),
                                        self.paths, systemd=systemd)
        controller.desktop_hud = self.overlay
        with mock.patch.object(controller, "_client", side_effect=AssertionError("wallpaper IPC called")):
            controller.start_hud()
            self.assertTrue(controller.refresh_hud("*"))
            controller.stop("DP-1")
        self.process.terminate.assert_not_called()
        systemd.stop_output.assert_called_once_with("DP-1")

    def test_shutdown_only_removes_owned_runtime_file(self):
        self.overlay.start({"enabled": True})
        sibling = self.overlay.state_file.parent / "unrelated.json"
        sibling.write_text("keep")
        self.overlay.close()
        self.process.terminate.assert_called_once()
        self.assertFalse(self.overlay.state_file.exists())
        self.assertTrue(sibling.exists())

    def test_wildcard_preview_uses_connected_screens_without_wallpaper_assignments(self):
        from mpvpaper_engine.monitors import MonitorInfo
        controller = PlaybackController(normalize_v2_config({"schema_version": 2}), self.paths,
                                        monitor_detector=lambda: [MonitorInfo("DP-3")])
        controller.refresh_hud = mock.Mock(return_value=True)
        self.assertEqual(controller.preview_hud("*", {"enabled": True}), {"previewed": ["DP-3"]})


if __name__ == "__main__":
    unittest.main()
