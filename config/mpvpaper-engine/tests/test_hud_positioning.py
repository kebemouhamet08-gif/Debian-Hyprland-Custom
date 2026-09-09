from pathlib import Path
import sys
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.hud_positioning import (  # noqa: E402
    Rect, nearest_free_position, resolve_position, safe_area,
)


class HudPositioningTests(unittest.TestCase):
    def test_safe_area_accounts_for_top_and_bottom_panels(self):
        screen = Rect(0, 0, 1920, 1080)
        result = safe_area(screen, [Rect(0, 0, 1920, 36), Rect(0, 1040, 600, 40)], 10)
        self.assertEqual(result.y, 46)
        self.assertEqual(result.bottom, 1030)

    def test_nearest_free_position_avoids_obstacle(self):
        screen = Rect(0, 0, 1000, 700)
        result = nearest_free_position(
            Rect(400, 250, 200, 150), screen, [Rect(350, 200, 300, 250)],
        )
        self.assertFalse(result.intersects(Rect(350, 200, 300, 250)))

    def test_resolve_position_clamps_to_safe_area(self):
        screen = Rect(0, 0, 1920, 1080)
        bounds = Rect(0, 60, 1920, 1020)
        x, y = resolve_position(0.5, 0.0, screen, (300, 200), bounds)
        self.assertGreaterEqual(y, 0.0)
        self.assertGreaterEqual(y, (60 + 100) / 1080 - 0.01)


if __name__ == "__main__":
    unittest.main()
