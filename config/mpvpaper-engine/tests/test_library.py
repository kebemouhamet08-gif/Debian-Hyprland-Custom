import importlib.util
import json
from contextlib import closing
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
SPEC = importlib.util.spec_from_file_location(
    "mpvpaper_engine_gui", MODULE_DIR / "mpvpaper-engine.py"
)
ENGINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENGINE)

from mpvpaper_engine.library import Library, LibraryError  # noqa: E402
from mpvpaper_engine.metadata import MediaMetadata  # noqa: E402
from mpvpaper_engine.models import MediaType  # noqa: E402
from mpvpaper_engine.paths import EnginePaths  # noqa: E402


class LibraryTests(unittest.TestCase):
    def test_media_kind_separates_images_and_videos(self):
        self.assertEqual(ENGINE.media_kind(Path("wallpaper.MP4")), "video")
        self.assertEqual(ENGINE.media_kind(Path("wallpaper.WebP")), "image")
        self.assertIsNone(ENGINE.media_kind(Path("notes.txt")))

    def test_media_filter_combines_category_and_search(self):
        video = Path("Frieren Night.mp4")
        image = Path("Frieren Still.png")
        self.assertTrue(ENGINE.media_matches_filter(video, "video", "frieren"))
        self.assertFalse(ENGINE.media_matches_filter(video, "image", "frieren"))
        self.assertTrue(ENGINE.media_matches_filter(image, "image", "still"))
        self.assertFalse(ENGINE.media_matches_filter(image, "image", "night"))

    def test_deletion_is_limited_to_managed_libraries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "library"
            library.mkdir()
            inside = library / "wallpaper.jpg"
            outside = root / "outside.jpg"
            inside.write_bytes(b"image")
            outside.write_bytes(b"image")

            self.assertEqual(
                ENGINE.validate_deletable_media(inside, (library,)), inside.resolve()
            )
            with self.assertRaisesRegex(ValueError, "bibliothèque gérée"):
                ENGINE.validate_deletable_media(outside, (library,))

    def test_assigned_wallpaper_cannot_be_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory)
            wallpaper = library / "active.webm"
            wallpaper.write_bytes(b"video")
            with self.assertRaisesRegex(ValueError, "actuellement assigné"):
                ENGINE.validate_deletable_media(
                    wallpaper, (library,), (wallpaper,)
                )


def core_paths(root):
    root = Path(root)
    return EnginePaths.from_environment({
        "HOME": str(root / "home"), "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"), "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_RUNTIME_DIR": str(root / "runtime"),
    })


class CoreLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.paths = core_paths(self.temporary.name)
        self.probe_calls = []

        def probe(path):
            self.probe_calls.append(path)
            return MediaMetadata(
                MediaType.IMAGE if path.suffix == ".png" else MediaType.VIDEO,
                None if path.suffix == ".png" else 10.0,
                1920, 1080, None if path.suffix == ".png" else 30.0,
                "png" if path.suffix == ".png" else "h264", None, 1000,
            )

        self.library = Library(self.paths, probe=probe)
        self.media_root = Path(self.temporary.name) / "wallpapers"
        self.media_root.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def media(self, name="night.mp4", content=b"media"):
        path = self.media_root / name
        path.write_bytes(content)
        return path

    def test_initialize_creates_required_tables_separately(self):
        self.library.initialize()
        import sqlite3
        with closing(sqlite3.connect(self.paths.library_db)) as connection:
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
        self.assertTrue({
            "wallpapers", "tags", "wallpaper_tags", "playlists", "playlist_items",
            "history", "cache_entries", "schema_migrations",
        }.issubset(tables))
        self.assertFalse(self.paths.recommendations_db.exists())
        self.assertEqual(self.paths.library_db.stat().st_mode & 0o777, 0o600)

    def test_import_and_get_wallpaper(self):
        path = self.media()
        wallpaper = self.library.import_file(path)
        restored = self.library.get(wallpaper.id)
        self.assertEqual(restored.path, path.resolve())
        self.assertEqual(restored.width, 1920)
        self.assertEqual(restored.media_type, MediaType.VIDEO)

    def test_unchanged_file_is_not_probed_again(self):
        path = self.media()
        self.library.import_file(path)
        self.library.import_file(path)
        self.assertEqual(len(self.probe_calls), 1)

    def test_changed_file_is_reprobed(self):
        path = self.media(content=b"a")
        self.library.import_file(path)
        path.write_bytes(b"changed")
        self.library.import_file(path)
        self.assertEqual(len(self.probe_calls), 2)

    def test_search_type_and_favorites(self):
        night = self.library.import_file(self.media("Night Sky.mp4"))
        self.library.import_file(self.media("Forest.png"))
        self.library.set_favorite(night.id, True)
        results = self.library.search("night", media_type="video", favorites_only=True)
        self.assertEqual([item.id for item in results], [night.id])

    def test_missing_file_is_marked_but_not_removed(self):
        path = self.media()
        wallpaper = self.library.import_file(path)
        path.unlink()
        result = self.library.scan((self.media_root,))
        self.assertEqual(result["missing"], 1)
        self.assertTrue(self.library.get(wallpaper.id).missing)

    def test_duplicate_uses_bounded_content_signature(self):
        first = self.library.import_file(self.media("one.mp4", b"duplicate"))
        second_path = self.media("two.mp4", b"duplicate")
        duplicate = self.library.find_duplicate(second_path)
        self.assertEqual(duplicate.id, first.id)

    def test_rebuild_thumbnail_updates_database(self):
        wallpaper = self.library.import_file(self.media())
        destination = self.paths.thumbnail_dir / "made.jpg"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"jpg")
        self.library.thumbnail_builder = lambda path, root: destination
        self.assertEqual(self.library.rebuild_thumbnail(wallpaper.id), destination)
        self.assertEqual(self.library.get(wallpaper.id).thumbnail_path, destination)

    def test_delete_refuses_outside_or_active_media(self):
        wallpaper = self.library.import_file(self.media())
        with self.assertRaises(LibraryError):
            self.library.delete_to_trash(wallpaper.id, library_roots=(Path("/elsewhere"),))
        with self.assertRaises(LibraryError):
            self.library.delete_to_trash(
                wallpaper.id, library_roots=(self.media_root,),
                protected_paths=(wallpaper.path,),
            )

    def test_delete_to_trash_is_explicit_and_marks_missing(self):
        wallpaper = self.library.import_file(self.media())

        def trash(command, **_options):
            Path(command[-1]).unlink()
            return subprocess.CompletedProcess(command, 0, "", "")

        self.library.trash_runner = trash
        self.library.delete_to_trash(wallpaper.id, library_roots=(self.media_root,))
        self.assertTrue(self.library.get(wallpaper.id).missing)


if __name__ == "__main__":
    unittest.main()
