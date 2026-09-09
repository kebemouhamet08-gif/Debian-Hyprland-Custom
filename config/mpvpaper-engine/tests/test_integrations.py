import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, MODULE_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CTL = load("mpvpaper_enginectl_integrations", "mpvpaper-enginectl.py")
WAYBAR = load("mpvpaper_engine_waybar", "mpvpaper-engine-waybar.py")


class IntegrationTests(unittest.TestCase):
    def test_library_list_json_has_stable_fields(self):
        wallpaper = mock.Mock(
            id=4, title="Night", path=Path("/wall/night.mp4"),
            media_type=mock.Mock(value="video"), width=1920, height=1080,
            fps=30.0, duration=12.0, favorite=True, missing=False,
        )
        output = io.StringIO()
        with mock.patch.object(CTL, "Library") as library, contextlib.redirect_stdout(output):
            library.return_value.list.return_value = [wallpaper]
            self.assertEqual(CTL.library_list_action(True), 0)
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["wallpapers"][0]["type"], "video")
        self.assertEqual(payload["wallpapers"][0]["id"], 4)

    def test_waybar_json_contains_wallpaper_output_status_and_profile(self):
        state = {"outputs": {"DP-1": {
            "status": "playing", "title": "Night", "performance_profile": "eco",
        }}}
        output = io.StringIO()
        with mock.patch.object(WAYBAR, "EngineClient") as client, \
                contextlib.redirect_stdout(output):
            client.return_value.get_state.return_value = state
            self.assertEqual(WAYBAR.main(), 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["class"], "playing")
        self.assertIn("DP-1 · Night · playing · ECO", payload["tooltip"])

    def test_waybar_snapshot_fallback_is_valid_json(self):
        output = io.StringIO()
        with mock.patch.object(WAYBAR, "EngineClient") as client, \
                mock.patch.object(WAYBAR, "read_state") as read, \
                mock.patch.object(WAYBAR, "state_to_dict", return_value={"outputs": {}}), \
                contextlib.redirect_stdout(output):
            from mpvpaper_engine.ipc import EngineUnavailableError
            client.return_value.get_state.side_effect = EngineUnavailableError("offline")
            self.assertEqual(WAYBAR.main(), 0)
        self.assertEqual(json.loads(output.getvalue())["class"], "stopped")
        read.assert_called_once()


if __name__ == "__main__":
    unittest.main()
