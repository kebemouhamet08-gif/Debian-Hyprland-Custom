from pathlib import Path
import sys
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.hud_editor_geometry import (  # noqa: E402
    canvas_from_normalized, normalized_from_canvas,
)


class HudEditorGeometryTests(unittest.TestCase):
    def test_normalized_coordinates_round_trip_with_letterboxing(self):
        monitor = {"width": 1920, "height": 1080}
        point = canvas_from_normalized(0.25, 0.75, monitor, 800, 600)
        self.assertAlmostEqual(
            normalized_from_canvas(*point, monitor, 800, 600)[0], 0.25
        )
        self.assertAlmostEqual(
            normalized_from_canvas(*point, monitor, 800, 600)[1], 0.75
        )

    def test_canvas_coordinates_are_clamped_to_editor_ranges(self):
        monitor = {"width": 1366, "height": 768}
        self.assertEqual(
            normalized_from_canvas(-100, -100, monitor, 800, 400), (0.0, 0.0)
        )
