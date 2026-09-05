from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.paths import EnginePaths  # noqa: E402
from mpvpaper_engine.theme_sync import (  # noqa: E402
    Palette, ThemeSync, extract_palette, palette_from_rgb,
)


def paths(root):
    root = Path(root)
    return EnginePaths.from_environment({
        "HOME": str(root), "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"), "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_RUNTIME_DIR": str(root / "runtime"),
    })


class ThemeSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.paths = paths(self.temp.name)
        self.media = Path(self.temp.name) / "wall.mp4"
        self.media.write_bytes(b"video")

    def tearDown(self):
        self.temp.cleanup()

    def test_palette_quantizes_and_selects_contrast(self):
        palette = palette_from_rgb(bytes([0, 0, 0, 255, 255, 255] * 4), self.media, 1)
        self.assertEqual(palette.background, "#000000")
        self.assertEqual(palette.foreground, "#f8f8f8")

    def test_extract_uses_one_frame_for_image_and_bounds_video_to_four(self):
        image = Path(self.temp.name) / "still.png"
        image.write_bytes(b"image")
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, b"\0\0\0" * 1024, b""))
        self.assertEqual(extract_palette(image, frames=4, runner=runner).frames, 1)
        self.assertIn("1", runner.call_args.args[0])
        extract_palette(self.media, frames=99, runner=runner)
        self.assertIn("4", runner.call_args.args[0])

    def test_extract_accepts_extensionless_video_wallpaper(self):
        current = Path(self.temp.name) / ".wallpaper_current"
        current.write_bytes(b"video")
        runner = mock.Mock(side_effect=[
            subprocess.CompletedProcess([], 0, "video\n", ""),
            subprocess.CompletedProcess([], 0, b"\0\0\0" * 4096, b""),
        ])

        palette = extract_palette(current, runner=runner)

        self.assertEqual(palette.frames, 4)
        self.assertEqual(runner.call_count, 2)

    def test_off_mode_has_no_side_effect(self):
        sync = ThemeSync(self.paths, extractor=mock.Mock(), runner=mock.Mock())
        self.assertFalse(sync.apply(self.media, mode="off").applied)
        sync.extractor.assert_not_called()

    def test_integrations_are_failure_isolated_and_state_is_written(self):
        palette = Palette(("#101010", "#eeeeee"), "#eeeeee", "#101010", str(self.media), 4)
        runner = mock.Mock(side_effect=[
            OSError("no waybar"),
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 1, "", "no wallust"),
        ])
        result = ThemeSync(
            self.paths, extractor=lambda _source, frames: palette, runner=runner
        ).apply(self.media)
        self.assertTrue(result.applied)
        self.assertTrue(result.integrations["waybar"].startswith("failed:"))
        self.assertEqual(result.integrations["nova"], "ok")
        self.assertTrue(self.paths.palette_dir.joinpath("current.json").is_file())

    def test_same_wallpaper_is_guarded_across_instances(self):
        palette = Palette(("#000000",), "#000000", "#000000", str(self.media), 2)
        first = ThemeSync(self.paths, extractor=lambda _source, frames: palette,
                          runner=lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "", ""))
        self.assertTrue(first.apply(self.media, profile="eco").applied)
        second = ThemeSync(self.paths, extractor=mock.Mock(), runner=mock.Mock())
        result = second.apply(self.media)
        self.assertFalse(result.applied)
        second.extractor.assert_not_called()

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            ThemeSync(self.paths).apply(self.media, mode="sometimes")


if __name__ == "__main__":
    unittest.main()
