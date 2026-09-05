from pathlib import Path
import subprocess
import sys
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.models import AnimatedPreview, PerformanceMode  # noqa: E402
from mpvpaper_engine.profiles import (  # noqa: E402
    HardwareContext,
    detect_hwdec,
    effective_settings,
    mpv_option_fragments,
    select_auto,
)


class ProfileTests(unittest.TestCase):
    def context(self, **changes):
        values = {
            "cpu_count": 4, "ram_gib": 8, "total_output_pixels": 2_073_600,
            "gpu_class": "integrated", "available_hwdec": ("vaapi",),
        }
        values.update(changes)
        return HardwareContext(**values)

    def test_eco_profile(self):
        profile = effective_settings("eco")
        self.assertEqual(profile.fps_limit, 24)
        self.assertEqual(profile.render_height, 720)
        self.assertEqual(profile.animated_preview, AnimatedPreview.OFF)
        self.assertTrue(profile.pause_on_fullscreen)

    def test_balanced_profile(self):
        profile = effective_settings("balanced")
        self.assertEqual(profile.fps_limit, 30)
        self.assertEqual(profile.render_height, 1080)
        self.assertEqual(profile.theme_analysis_frames, 4)

    def test_quality_profile(self):
        profile = effective_settings("quality")
        self.assertIsNone(profile.fps_limit)
        self.assertIsNone(profile.render_height)
        self.assertFalse(profile.pause_on_fullscreen)

    def test_auto_uses_eco_on_battery(self):
        selected, reason = select_auto(self.context(on_battery=True))
        self.assertEqual(selected, PerformanceMode.ECO)
        self.assertIn("battery", reason)

    def test_auto_uses_eco_for_low_end(self):
        selected, _ = select_auto(self.context(cpu_count=2, ram_gib=3))
        self.assertEqual(selected, PerformanceMode.ECO)

    def test_auto_uses_eco_for_integrated_multi_4k(self):
        selected, _ = select_auto(self.context(total_output_pixels=16_000_000))
        self.assertEqual(selected, PerformanceMode.ECO)

    def test_auto_uses_quality_for_capable_discrete_machine(self):
        selected, _ = select_auto(self.context(
            cpu_count=8, ram_gib=16, gpu_class="discrete",
        ))
        self.assertEqual(selected, PerformanceMode.QUALITY)

    def test_auto_defaults_to_balanced(self):
        selected, _ = select_auto(self.context())
        self.assertEqual(selected, PerformanceMode.BALANCED)

    def test_auto_never_upscales_or_exceeds_source_fps(self):
        profile = effective_settings("auto", self.context(
            media_height=720, media_fps=25,
        ))
        self.assertEqual(profile.effective, PerformanceMode.BALANCED)
        self.assertEqual(profile.render_height, 720)
        self.assertEqual(profile.fps_limit, 25)

    def test_hwdec_help_is_parsed_without_forcing_backend(self):
        runner = lambda command, **options: subprocess.CompletedProcess(
            command, 0, "vaapi-copy\nnvdec\n", "",
        )
        self.assertEqual(detect_hwdec(runner), ("vaapi", "nvdec"))
        self.assertEqual(effective_settings("quality").hwdec, "auto-safe")

    def test_failed_hwdec_probe_returns_empty(self):
        runner = lambda command, **options: subprocess.CompletedProcess(command, 1, "", "bad")
        self.assertEqual(detect_hwdec(runner), ())

    def test_mpv_fragments_expose_effective_limits(self):
        options = mpv_option_fragments(effective_settings("eco"))
        self.assertIn("hwdec=auto-safe", options)
        self.assertIn("vf-add=fps=fps=24", options)
        self.assertTrue(any("scale=-2:720" in option for option in options))

    def test_invalid_profile_is_rejected(self):
        with self.assertRaises(ValueError):
            effective_settings("turbo")


if __name__ == "__main__":
    unittest.main()
