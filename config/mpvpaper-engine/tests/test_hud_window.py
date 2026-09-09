from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1]))
from mpvpaper_engine.hud_window import gdk_monitors


class HudWindowTests(unittest.TestCase):
    def test_gdk_fallback_uses_saved_output_name(self):
        rectangle = mock.Mock(x=0, y=0, width=1920, height=1080)
        monitor = mock.Mock()
        monitor.get_geometry.return_value = rectangle
        monitor.get_model.return_value = "Built-in display"
        display = mock.Mock()
        display.get_n_monitors.return_value = 1
        display.get_monitor.return_value = monitor

        result = gdk_monitors(display, {"outputs": {"eDP-1": {"enabled": True}}})

        self.assertEqual(result[0].name, "eDP-1")
        self.assertEqual((result[0].width, result[0].height), (1920, 1080))


if __name__ == "__main__":
    unittest.main()
