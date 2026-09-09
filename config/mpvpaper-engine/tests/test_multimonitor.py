from pathlib import Path
import sys
import unittest
from unittest import mock


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.config import normalize_v2_config  # noqa: E402
from mpvpaper_engine.models import PlaybackState  # noqa: E402
from mpvpaper_engine.monitors import MonitorInfo, MonitorManager  # noqa: E402


class MultiMonitorTests(unittest.TestCase):
    def config(self, mode="independent"):
        return normalize_v2_config({
            "schema_version": 2, "mode": mode,
            "outputs": {
                "eDP-1": {"wallpaper": "/wall/laptop.mp4"},
                "HDMI-A-1": {"wallpaper": "/wall/external.mp4"},
            },
        })

    def test_independent_keeps_distinct_wallpapers(self):
        config = self.config()
        self.assertNotEqual(
            config.outputs["eDP-1"]["wallpaper"],
            config.outputs["HDMI-A-1"]["wallpaper"],
        )

    def test_same_uses_global_logical_target(self):
        manager = MonitorManager(self.config("same"))
        targets = manager.targets([MonitorInfo("eDP-1"), MonitorInfo("HDMI-A-1")])
        self.assertEqual(targets, ["*"])

    def test_disconnected_profile_survives_reconciliation(self):
        config = self.config()
        MonitorManager(config).reconcile([MonitorInfo("eDP-1")])
        self.assertEqual(config.outputs["HDMI-A-1"]["wallpaper"], "/wall/external.mp4")

    def test_sync_corrects_only_drift_above_threshold(self):
        config = self.config("sync")
        playback = mock.Mock()
        playback.get_state.side_effect = [
            PlaybackState("eDP-1", position=10.0),
            PlaybackState("HDMI-A-1", position=10.35),
        ]
        corrected = MonitorManager(config, playback=playback).correct_sync_drift([
            MonitorInfo("eDP-1"), MonitorInfo("HDMI-A-1"),
        ])
        self.assertAlmostEqual(corrected["HDMI-A-1"], 0.35)
        playback.seek.assert_called_once_with("HDMI-A-1", 10.0)

    def test_sync_ignores_small_drift(self):
        config = self.config("sync")
        playback = mock.Mock()
        playback.get_state.side_effect = [
            PlaybackState("eDP-1", position=10.0),
            PlaybackState("HDMI-A-1", position=10.1),
        ]
        corrected = MonitorManager(config, playback=playback).correct_sync_drift([
            MonitorInfo("eDP-1"), MonitorInfo("HDMI-A-1"),
        ])
        self.assertEqual(corrected, {})
        playback.seek.assert_not_called()


if __name__ == "__main__":
    unittest.main()
