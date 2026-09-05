from pathlib import Path
import sys
import tempfile
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.hud import HudSettings, HudManager, make_ass  # noqa: E402


class HudTests(unittest.TestCase):
    def test_ass_contains_live_clock_fields_and_styles(self):
        content = make_ass(1920, 1080, HudSettings(), {
            "text": "#FFFFFF", "muted": "#CCCCCC", "accent": "#FF3344",
        })
        self.assertIn("GOOD ", content)
        self.assertIn("Style: Anurati", content)
        self.assertIn("Noto Sans CJK JP", content)
        self.assertIn("ムハメト・ケベ", content)

    def test_disabled_elements_do_not_shift_styles(self):
        content = make_ass(1920, 1080, HudSettings(day=False, japanese=False), {
            "text": "#FFFFFF", "muted": "#CCCCCC", "accent": "#FF3344",
        })
        self.assertNotIn(",Anurati,,", content)
        self.assertNotIn("こんばんは", content)
        self.assertIn(",Greeting,,", content)

    def test_manager_writes_palette_aware_file(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            waybar = root / "config" / "waybar"
            waybar.mkdir(parents=True)
            (waybar / "panel-colors.css").write_text(
                "@define-color text #EEEEEE;\n@define-color muted #AAAAAA;\n"
                "@define-color accent #FF3344;\n", encoding="utf-8"
            )
            manager = HudManager(root / "cache", root / "config" / "mpvpaper-engine")
            manager.configure({"enabled": True})
            path = manager.render("eDP-1")
            self.assertIsNotNone(path)
            self.assertIn("&H004433FF", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()