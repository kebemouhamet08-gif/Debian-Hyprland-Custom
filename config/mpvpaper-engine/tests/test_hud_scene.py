from pathlib import Path
import sys
import unittest
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parents[1]))
from mpvpaper_engine.hud import normalized_hud, effective_hud, settings_from_config, preview_settings
from mpvpaper_engine.hud_scene import geometry, logical_screen, entries, draw
from mpvpaper_engine.hud_positioning import Rect, safe_area
from mpvpaper_engine.monitors import MonitorInfo


class HudSceneTests(unittest.TestCase):
    def test_global_preview_has_same_output_precedence_as_saved_settings(self):
        base = {"scale": 1, "outputs": {"DP-1": {"scale": 1.5}}}
        draft = {"scale": .75}
        self.assertEqual(preview_settings(base, "DP-1", {"*": draft})["scale"], 1.5)
        self.assertEqual(preview_settings(base, "DP-2", {"*": draft})["scale"], .75)
        self.assertEqual(preview_settings(base, "DP-1", {"DP-1": draft})["scale"], .75)

    def test_invalid_numeric_field_does_not_reset_other_controls(self):
        value = normalized_hud({"position": {"x": .73, "y": .61},
                                "scale": "bad", "opacity": float("nan"),
                                "safe_margin": None})
        self.assertEqual(value["position"], {"x": .73, "y": .61})
        self.assertEqual((value["scale"], value["opacity"], value["safe_margin"]), (1, 1, 24))
        self.assertEqual(settings_from_config({"opacity": 0}).opacity, 0)
        malformed = normalized_hud({"anchor": [], "colors": {"mode": {}, "custom": {"accent": float("nan")}}})
        self.assertEqual(malformed["anchor"], "center")
        self.assertEqual(malformed["colors"], {"mode": "system", "custom": {}})

    def test_output_partial_custom_color_preserves_other_colors(self):
        config = {"colors": {"mode": "custom", "custom": {"primary": "#123456", "accent": "#445566"}},
                  "outputs": {"DP-1": {"colors": {"custom": {"accent": "#ABCDEF"}}}}}
        effective = effective_hud(config, "DP-1")
        self.assertEqual(effective["colors"]["custom"], {"primary": "#123456", "accent": "#ABCDEF"})
        self.assertNotIn("outputs", effective)

    def test_exact_position_when_avoidance_and_snap_disabled(self):
        screen = Rect(-1280, 120, 1280, 720)
        settings = {"position": {"x": .125, "y": .875}, "avoid_layers": False, "snap": False}
        result = geometry(settings, screen, [Rect(-1280, 120, 1280, 50)])
        self.assertEqual(result["resolved"], settings["position"])
        self.assertEqual(result["rect"].x + result["rect"].width / 2, -1120)

    def test_anchor_is_respected(self):
        screen = Rect(0, 0, 1920, 1080)
        for anchor, fractions in {"top-left": (0, 0), "center": (.5, .5), "bottom-right": (1, 1)}.items():
            data = {"anchor": anchor, "position": {"x": .5, "y": .5}, "avoid_layers": False, "snap": False}
            rect = geometry(data, screen)["rect"]
            self.assertEqual(rect.x + rect.width * fractions[0], 960)
            self.assertEqual(rect.y + rect.height * fractions[1], 540)

    def test_panel_at_corner_does_not_consume_entire_screen(self):
        area = safe_area(Rect(0, 0, 1920, 1080), [Rect(0, 0, 1920, 36)], 24)
        self.assertEqual(area, Rect(24, 60, 1872, 996))

    def test_real_hyprland_floating_waybar_geometry(self):
        from mpvpaper_engine.hud_layers import parse_layers, panel_rects
        layers = parse_layers({"eDP-1": {"levels": {"2": [
            {"x": 8, "y": 5, "w": 1904, "h": 42, "namespace": "waybar"}]}}})
        panels = panel_rects(layers, "eDP-1")
        self.assertEqual(len(panels), 1)
        area = safe_area(Rect(0, 0, 1920, 1080), panels, 24)
        self.assertEqual(area, Rect(24, 71, 1872, 985))

    def test_hidpi_and_rotated_monitor_use_logical_pixels(self):
        screen = logical_screen(MonitorInfo("DP-1", 3840, 2160, x=-1920, y=0, scale=2))
        self.assertEqual(screen, Rect(-1920, 0, 1920, 1080))
        rotated = logical_screen(MonitorInfo("DP-1", 1920, 1080, scale=1, transform=1))
        self.assertEqual(rotated, Rect(0, 0, 1080, 1920))

    def test_scale_and_enabled_elements_change_real_scene(self):
        data = {"enabled": True, "scale": 1.5, "elements": {"time": False}, "username": "Test"}
        rect = geometry(data, Rect(0, 0, 1920, 1080))["rect"]
        self.assertEqual((rect.width, rect.height), (930, 840))
        text = [row[0] for row in entries(data, datetime(2026, 1, 1, 10, 12))]
        self.assertNotIn("10:12", text)
        self.assertIn("GOOD MORNING", text)

    def test_transparent_and_disabled_render_really_draw_no_pixels(self):
        import cairo
        for data in ({"enabled": True, "opacity": 0}, {"enabled": False}):
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 640, 600)
            draw(cairo.Context(surface), data, Rect(0, 0, 620, 560))
            surface.flush()
            self.assertFalse(any(surface.get_data()))
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 640, 600)
        draw(cairo.Context(surface), {"enabled": True}, Rect(0, 0, 620, 560))
        surface.flush()
        self.assertTrue(any(surface.get_data()))


if __name__ == "__main__":
    unittest.main()
