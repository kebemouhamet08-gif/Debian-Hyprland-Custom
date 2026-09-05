from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.history import HistoryManager  # noqa: E402
from mpvpaper_engine.library import Library  # noqa: E402
from mpvpaper_engine.metadata import MediaMetadata  # noqa: E402
from mpvpaper_engine.models import MediaType, PlaylistMode  # noqa: E402
from mpvpaper_engine.paths import EnginePaths  # noqa: E402
from mpvpaper_engine.playlists import PlaylistManager  # noqa: E402


def paths_for(root):
    root = Path(root)
    return EnginePaths.from_environment({
        "HOME": str(root / "home"), "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"), "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_RUNTIME_DIR": str(root / "runtime"),
    })


class HighestWeightRng:
    def choice(self, values):
        return values[-1]

    def choices(self, values, weights, k):
        return [values[weights.index(max(weights))]]


class PlaylistTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.paths = paths_for(self.temporary.name)
        metadata = MediaMetadata(MediaType.VIDEO, 10, 1920, 1080, 30, "h264", None, 1)
        self.library = Library(self.paths, probe=lambda path: metadata)
        self.wallpapers = []
        for name in ("one.mp4", "two.mp4", "three.mp4"):
            path = Path(self.temporary.name) / name
            path.write_bytes(name.encode())
            self.wallpapers.append(self.library.import_file(path))
        self.manager = PlaylistManager(self.library, HighestWeightRng())

    def tearDown(self):
        self.temporary.cleanup()

    def playlist(self, mode="sequential", interval=None):
        playlist = self.manager.create("Test", mode, interval)
        for wallpaper in self.wallpapers:
            self.manager.add(playlist.id, wallpaper.id)
        return playlist

    def test_create_rename_list_and_delete(self):
        playlist = self.manager.create("Night")
        self.assertEqual(self.manager.rename(playlist.id, "Evening").name, "Evening")
        self.assertEqual([item.name for item in self.manager.list()], ["Evening"])
        self.manager.delete(playlist.id)
        self.assertEqual(self.manager.list(), [])

    def test_invalid_name_mode_and_interval(self):
        with self.assertRaises(ValueError):
            self.manager.create(" ")
        with self.assertRaises(ValueError):
            self.manager.create("Bad", "chaos")
        with self.assertRaises(ValueError):
            self.manager.create("Bad", interval_seconds=12)

    def test_add_remove_and_order(self):
        playlist = self.playlist()
        self.manager.remove(playlist.id, self.wallpapers[1].id)
        self.assertEqual(
            [item.id for item in self.manager.items(playlist.id)],
            [self.wallpapers[0].id, self.wallpapers[2].id],
        )

    def test_reorder_requires_exact_membership(self):
        playlist = self.playlist()
        order = [item.id for item in reversed(self.wallpapers)]
        self.manager.reorder(playlist.id, order)
        self.assertEqual([item.id for item in self.manager.items(playlist.id)], order)
        with self.assertRaises(ValueError):
            self.manager.reorder(playlist.id, order[:-1])

    def test_sequential_wraps(self):
        playlist = self.playlist()
        selected = self.manager.next(playlist.id, current_id=self.wallpapers[-1].id)
        self.assertEqual(selected.id, self.wallpapers[0].id)

    def test_shuffle_avoids_current_when_possible(self):
        playlist = self.playlist("shuffle")
        selected = self.manager.next(playlist.id, current_id=self.wallpapers[-1].id)
        self.assertNotEqual(selected.id, self.wallpapers[-1].id)

    def test_smart_excludes_recent_items(self):
        playlist = self.playlist("smart")
        history = HistoryManager(self.library)
        history.start(self.wallpapers[0].id, "DP-1", "playlist")
        history.start(self.wallpapers[1].id, "DP-1", "playlist")
        selected = self.manager.next(playlist.id, output="DP-1", recent_count=2)
        self.assertEqual(selected.id, self.wallpapers[2].id)

    def test_smart_favorite_and_rare_weights(self):
        playlist = self.playlist("smart")
        favorite = self.library.set_favorite(self.wallpapers[1].id, True)
        selected = self.manager.next(playlist.id, recent_count=0)
        self.assertEqual(selected.id, favorite.id)

    def test_missing_items_are_not_eligible(self):
        playlist = self.playlist()
        self.library.mark_missing(self.wallpapers[0].id)
        ids = [item.id for item in self.manager.items(playlist.id)]
        self.assertNotIn(self.wallpapers[0].id, ids)

    def test_empty_playlist_returns_none(self):
        playlist = self.manager.create("Empty")
        self.assertIsNone(self.manager.next(playlist.id))

    def test_timer_deadline_and_events(self):
        playlist = self.manager.create("Timer", interval_seconds=300)
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertEqual((self.manager.next_deadline(playlist.id, now) - now).seconds, 300)
        self.assertTrue(self.manager.should_advance("login"))
        self.assertTrue(self.manager.should_advance("unlock"))
        self.assertFalse(self.manager.should_advance("poll"))

    def test_configure_mode_and_interval(self):
        playlist = self.manager.create("Config")
        updated = self.manager.configure(
            playlist.id, mode=PlaylistMode.SMART, interval_seconds=600
        )
        self.assertEqual(updated.mode, PlaylistMode.SMART)
        self.assertEqual(updated.interval_seconds, 600)


if __name__ == "__main__":
    unittest.main()
