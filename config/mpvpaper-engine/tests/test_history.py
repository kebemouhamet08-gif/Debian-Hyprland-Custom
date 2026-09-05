from pathlib import Path
import sys
import tempfile
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.history import HistoryManager  # noqa: E402
from mpvpaper_engine.library import Library  # noqa: E402
from mpvpaper_engine.metadata import MediaMetadata  # noqa: E402
from mpvpaper_engine.models import MediaType  # noqa: E402
from mpvpaper_engine.paths import EnginePaths  # noqa: E402


def paths_for(root):
    root = Path(root)
    return EnginePaths.from_environment({
        "HOME": str(root / "home"), "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"), "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_RUNTIME_DIR": str(root / "runtime"),
    })


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.paths = paths_for(self.temporary.name)
        metadata = MediaMetadata(MediaType.VIDEO, 10, 1920, 1080, 30, "h264", None, 1)
        self.library = Library(self.paths, probe=lambda path: metadata)
        media = Path(self.temporary.name) / "wall.mp4"
        media.write_bytes(b"video")
        self.wallpaper = self.library.import_file(media)
        self.history = HistoryManager(self.library)

    def tearDown(self):
        self.temporary.cleanup()

    def test_start_records_reason_and_output(self):
        entry = self.history.start(self.wallpaper.id, "DP-1", "manual")
        self.assertEqual(entry.reason, "manual")
        self.assertEqual(entry.output, "DP-1")
        self.assertIsNone(entry.ended_at)

    def test_start_increments_usage(self):
        self.history.start(self.wallpaper.id, "DP-1", "random")
        updated = self.library.get(self.wallpaper.id)
        self.assertEqual(updated.usage_count, 1)
        self.assertIsNotNone(updated.last_used)

    def test_new_entry_closes_previous_on_same_output(self):
        first = self.history.start(self.wallpaper.id, "DP-1")
        self.history.start(self.wallpaper.id, "DP-1", "playlist")
        restored = next(item for item in self.history.list() if item.id == first.id)
        self.assertIsNotNone(restored.ended_at)

    def test_end_closes_entry(self):
        entry = self.history.start(self.wallpaper.id, "DP-1")
        self.assertIsNotNone(self.history.end(entry.id).ended_at)

    def test_unknown_entry_is_rejected(self):
        with self.assertRaises(KeyError):
            self.history.end(999)

    def test_output_filter(self):
        self.history.start(self.wallpaper.id, "DP-1")
        self.history.start(self.wallpaper.id, "HDMI-A-1")
        self.assertEqual(len(self.history.list(output="DP-1")), 1)

    def test_invalid_reason_and_output_are_rejected(self):
        with self.assertRaises(ValueError):
            self.history.start(self.wallpaper.id, "../../bad")
        with self.assertRaises(ValueError):
            self.history.start(self.wallpaper.id, "DP-1", "telemetry")


if __name__ == "__main__":
    unittest.main()
