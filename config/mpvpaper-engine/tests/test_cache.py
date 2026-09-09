import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.cache import (  # noqa: E402
    CacheManager,
    CacheSafetyError,
    DEFAULT_CATEGORY_QUOTAS,
    DEFAULT_TOTAL_QUOTA,
    SUGGESTION_MAX_AGE,
)
from mpvpaper_engine.paths import EnginePaths  # noqa: E402


def temporary_paths(root):
    root = Path(root)
    return EnginePaths.from_environment({
        "HOME": str(root / "home"), "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"), "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_RUNTIME_DIR": str(root / "runtime"),
    })


def make_file(path, size, accessed=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    if accessed is not None:
        os.utime(path, (accessed, accessed))
    return path


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.paths = temporary_paths(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_default_quotas(self):
        manager = CacheManager(self.paths)
        self.assertEqual(manager.total_quota, DEFAULT_TOTAL_QUOTA)
        self.assertEqual(manager.category_quotas, DEFAULT_CATEGORY_QUOTAS)
        self.assertEqual(manager.suggestion_max_age, SUGGESTION_MAX_AGE)

    def test_construction_and_stats_have_no_side_effect(self):
        stats = CacheManager(self.paths).stats()
        self.assertEqual(stats["total_size"], 0)
        self.assertFalse(self.paths.cache_home.exists())

    def test_stats_separate_categories(self):
        make_file(self.paths.suggestion_cache_dir / "a.jpg", 11)
        make_file(self.paths.thumbnail_dir / "b.jpg", 13)
        make_file(self.paths.temp_dir / "c.part", 17)
        stats = CacheManager(self.paths).stats()
        self.assertEqual(stats["total_size"], 41)
        self.assertEqual(stats["categories"]["suggestions"]["size"], 11)
        self.assertEqual(stats["categories"]["thumbnails"]["entries"], 1)

    def test_rebuild_index_is_private_and_atomic(self):
        make_file(self.paths.thumbnail_dir / "thumb.png", 7)
        manager = CacheManager(self.paths)
        result = manager.rebuild_index()
        data = json.loads(manager.index_file.read_text())
        self.assertEqual(result, {"entries": 1, "size": 7})
        self.assertEqual(data["entries"][0]["category"], "thumbnails")
        self.assertEqual(manager.index_file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.paths.cache_home.glob(".cache-index.json-*")), [])

    def test_clean_expired_removes_only_old_suggestions(self):
        now = time.time()
        old = make_file(self.paths.suggestion_cache_dir / "old.jpg", 5, now - SUGGESTION_MAX_AGE - 1)
        fresh = make_file(self.paths.suggestion_cache_dir / "fresh.jpg", 6, now)
        thumbnail = make_file(self.paths.thumbnail_dir / "old.jpg", 7, now - SUGGESTION_MAX_AGE - 1)
        result = CacheManager(self.paths).clean_expired(now=now)
        self.assertEqual(result, {"removed": 1, "reclaimed": 5})
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())
        self.assertTrue(thumbnail.exists())

    def test_category_quota_uses_lru_order(self):
        now = time.time()
        oldest = make_file(self.paths.thumbnail_dir / "old", 6, now - 20)
        newest = make_file(self.paths.thumbnail_dir / "new", 6, now - 10)
        manager = CacheManager(
            self.paths, total_quota=100,
            category_quotas={"thumbnails": 6},
        )
        result = manager.enforce_quotas()
        self.assertEqual(result["removed"], 1)
        self.assertFalse(oldest.exists())
        self.assertTrue(newest.exists())

    def test_total_quota_applies_across_categories(self):
        now = time.time()
        oldest = make_file(self.paths.suggestion_cache_dir / "old", 8, now - 20)
        newest = make_file(self.paths.thumbnail_dir / "new", 8, now - 10)
        manager = CacheManager(
            self.paths, total_quota=8,
            category_quotas={key: 100 for key in DEFAULT_CATEGORY_QUOTAS},
        )
        manager.enforce_quotas()
        self.assertFalse(oldest.exists())
        self.assertTrue(newest.exists())

    def test_clean_suggestions_does_not_touch_thumbnails(self):
        suggestion = make_file(self.paths.suggestion_cache_dir / "a", 2)
        thumbnail = make_file(self.paths.thumbnail_dir / "b", 3)
        CacheManager(self.paths).clean_suggestions()
        self.assertFalse(suggestion.exists())
        self.assertTrue(thumbnail.exists())

    def test_clean_category_and_clean_all(self):
        temporary = make_file(self.paths.temp_dir / "part", 2)
        palette = make_file(self.paths.palette_dir / "colors", 3)
        manager = CacheManager(self.paths)
        manager.clean_category("temporary")
        self.assertFalse(temporary.exists())
        self.assertTrue(palette.exists())
        manager.clean_all()
        self.assertFalse(palette.exists())

    def test_unknown_category_is_rejected(self):
        with self.assertRaises(ValueError):
            CacheManager(self.paths).clean_category("wallpapers")

    def test_outside_cache_is_never_a_deletion_target(self):
        outside = make_file(Path(self.temporary.name) / "wallpaper.mp4", 4)
        with self.assertRaises(CacheSafetyError):
            CacheManager(self.paths)._safe_candidate(outside)
        self.assertTrue(outside.exists())

    def test_library_target_through_symlink_is_refused(self):
        library = Path(self.temporary.name) / "library"
        wallpaper = make_file(library / "wallpaper.mp4", 4)
        link = self.paths.suggestion_cache_dir / "unsafe-link"
        link.parent.mkdir(parents=True)
        link.symlink_to(wallpaper)
        manager = CacheManager(self.paths, library_roots=(library,))
        with self.assertRaises(CacheSafetyError):
            manager.clean_suggestions()
        self.assertTrue(wallpaper.exists())
        self.assertTrue(link.is_symlink())


if __name__ == "__main__":
    unittest.main()
