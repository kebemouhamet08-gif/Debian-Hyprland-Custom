from pathlib import Path
import sys
import tempfile
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.waybar_theme import write_panel_colors  # noqa: E402


class WaybarThemeTests(unittest.TestCase):
    def test_generation_is_atomic_and_preserves_theme_overrides(self):
        with tempfile.TemporaryDirectory() as root:
            waybar = Path(root) / "waybar"
            waybar.mkdir()
            overrides = waybar / "theme-overrides.css"
            overrides.write_text("custom-rule", encoding="utf-8")
            changed = write_panel_colors(
                waybar,
                palette={
                    "accent": "#112233", "foreground": "#eeeeee",
                    "background": "#000000", "muted": "#888888",
                },
            )
            self.assertTrue(changed)
            self.assertIn("@define-color accent #112233;", (waybar / "panel-colors.css").read_text())
            self.assertEqual(overrides.read_text(), "custom-rule")
            self.assertFalse(write_panel_colors(
                waybar,
                palette={
                    "accent": "#112233", "foreground": "#eeeeee",
                    "background": "#000000", "muted": "#888888",
                },
            ))

    def test_wallust_colors_win_over_fallback_palette(self):
        with tempfile.TemporaryDirectory() as root:
            waybar = Path(root) / "waybar"
            wallust = waybar / "wallust"
            wallust.mkdir(parents=True)
            (wallust / "colors-waybar.css").write_text(
                "@define-color color13 #abcdef;\n"
                "@define-color foreground #ffffff;\n"
                "@define-color background #101010;\n"
                "@define-color color8 #888888;\n",
                encoding="utf-8",
            )
            write_panel_colors(waybar, palette={"accent": "#000000"})
            self.assertIn("@define-color accent #abcdef;", (waybar / "panel-colors.css").read_text())
