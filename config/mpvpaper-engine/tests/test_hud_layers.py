from pathlib import Path
import sys
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.hud_layers import parse_layers, panel_rects  # noqa: E402


class HudLayerTests(unittest.TestCase):
    def test_parse_layers_recognizes_panels_and_skips_unmapped(self):
        layers = parse_layers({
            "eDP-1": {"levels": {
                "top": [
                    {"namespace": "waybar", "geometry": {"x": 0, "y": 0, "w": 1920, "h": 36}},
                    {"namespace": "nwg-dock", "mapped": False,
                     "geometry": {"x": 20, "y": 1000, "w": 500, "h": 80}},
                ],
            }},
        })
        self.assertEqual(len(layers), 1)
        self.assertEqual(panel_rects(layers, "eDP-1")[0].height, 36)


if __name__ == "__main__":
    unittest.main()
