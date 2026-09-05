import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.config import normalize_v2_config  # noqa: E402
from mpvpaper_engine.models import OutputMode, PlaybackState, PlaybackStatus  # noqa: E402
from mpvpaper_engine.monitors import (  # noqa: E402
    MonitorError,
    MonitorInfo,
    MonitorManager,
    detect_monitors,
)


class MonitorTests(unittest.TestCase):
    def test_detect_hyprland_monitors_from_one_json_call(self):
        calls = []
        payload = [{
            "name": "eDP-1", "width": 1920, "height": 1080,
            "refreshRate": 60.0, "x": 0, "y": 0, "scale": 1.0,
            "focused": True,
        }]

        def runner(command, **_options):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

        monitors = detect_monitors(runner)
        self.assertEqual(len(calls), 1)
        self.assertEqual(monitors[0].name, "eDP-1")
        self.assertEqual(monitors[0].width, 1920)
        self.assertTrue(monitors[0].focused)

    def test_invalid_hyprctl_response_is_explicit(self):
        runner = lambda command, **options: subprocess.CompletedProcess(command, 0, "{}", "")
        with self.assertRaises(MonitorError):
            detect_monitors(runner)

    def test_invalid_output_entries_are_ignored(self):
        runner = lambda command, **options: subprocess.CompletedProcess(
            command, 0, '[{"name":"../../bad"},{"name":"DP-1"}]', "",
        )
        self.assertEqual([item.name for item in detect_monitors(runner)], ["DP-1"])

    def test_reconcile_preserves_disconnected_profiles(self):
        config = normalize_v2_config({
            "schema_version": 2,
            "outputs": {"eDP-1": {}, "HDMI-A-1": {}},
        })
        result = MonitorManager(config).reconcile([MonitorInfo("eDP-1")])
        self.assertEqual(result, {"HDMI-A-1": "unavailable", "eDP-1": "available"})
        self.assertIn("HDMI-A-1", config.outputs)

    def test_disconnect_marks_runtime_unavailable(self):
        config = normalize_v2_config({"schema_version": 2, "outputs": {"DP-1": {}}})
        state = mock.Mock()
        result = MonitorManager(config, state=state).handle_hotplug(
            [MonitorInfo("DP-1")], []
        )
        state.update_output.assert_called_once_with("DP-1", status=PlaybackStatus.UNAVAILABLE)
        self.assertEqual(result["disconnected"], ["DP-1"])

    def test_reconnect_restores_only_autostart_profile(self):
        config = normalize_v2_config({
            "schema_version": 2,
            "outputs": {"DP-1": {"wallpaper": "/wall/a.mp4", "autostart": True}},
        })
        playback = mock.Mock()
        result = MonitorManager(config, playback=playback).handle_hotplug(
            [], [MonitorInfo("DP-1")]
        )
        playback.play.assert_called_once_with("DP-1", "/wall/a.mp4")
        self.assertEqual(result["restored"], ["DP-1"])

    def test_disabled_mode_never_restores_hotplug(self):
        config = normalize_v2_config({
            "schema_version": 2, "mode": "disabled",
            "outputs": {"DP-1": {"wallpaper": "/wall/a.mp4", "autostart": True}},
        })
        playback = mock.Mock()
        MonitorManager(config, playback=playback).handle_hotplug([], [MonitorInfo("DP-1")])
        playback.play.assert_not_called()

    def test_targets_follow_mode(self):
        config = normalize_v2_config({
            "schema_version": 2, "outputs": {"DP-1": {}, "DP-2": {}},
        })
        manager = MonitorManager(config)
        monitors = [MonitorInfo("DP-1"), MonitorInfo("DP-2")]
        self.assertEqual(manager.targets(monitors), ["DP-1", "DP-2"])
        manager.set_mode("same")
        self.assertEqual(manager.targets(monitors), ["*"])
        manager.set_mode(OutputMode.DISABLED)
        self.assertEqual(manager.targets(monitors), [])

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            MonitorManager(normalize_v2_config({"schema_version": 2})).set_mode("mirror-magic")


if __name__ == "__main__":
    unittest.main()
