from pathlib import Path
from contextlib import closing
import sqlite3
import sys
import tempfile
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.paths import EnginePaths  # noqa: E402
from mpvpaper_engine.recommendations import RecommendationEngine  # noqa: E402


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.paths = EnginePaths.from_environment({"HOME": str(root)})
        self.paths.data_home.mkdir(parents=True)
        with closing(sqlite3.connect(self.paths.recommendations_db)) as connection:
            connection.executescript("""
                CREATE TABLE candidates(uri TEXT PRIMARY KEY,title TEXT,source TEXT,tags TEXT,
                  score REAL,views INTEGER,last_seen INTEGER,external_views INTEGER,external_likes INTEGER);
                CREATE TABLE tag_profile(tag TEXT PRIMARY KEY,weight REAL);
            """)
            connection.executemany("INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?,?)", [
                ("https://a/1", "Anime", "a", "anime blue", .1, 0, 0, 1000, 80),
                ("https://a/2", "City", "a", "city", .1, 0, 0, 10, 0),
                ("https://b/1", "Space", "b", "space blue", .1, 0, 0, 500, 20),
                ("https://c/1", "Nature", "c", "nature", .1, 0, 0, 50, 2),
            ])
            connection.commit()
        self.engine = RecommendationEngine(self.paths)

    def tearDown(self):
        self.temp.cleanup()

    def test_sources_and_diversified_results(self):
        self.assertEqual(self.engine.sources(), {"a": 2, "b": 1, "c": 1})
        results = self.engine.recommend(limit=4)
        self.assertEqual({item.source for item in results}, {"a", "b", "c"})

    def test_count_and_sources_are_configurable_and_persistent(self):
        values = self.engine.configure(enabled_sources=["a", "b"], limit=7)
        self.assertEqual(values["limit"], 7)
        self.assertEqual(RecommendationEngine(self.paths).settings(), values)
        self.assertEqual({item.source for item in self.engine.recommend()}, {"a", "b"})

    def test_feedback_changes_candidate_and_tag_weights(self):
        self.engine.feedback("https://a/1", 1)
        with closing(sqlite3.connect(self.paths.recommendations_db)) as connection:
            score, views = connection.execute(
                "SELECT score,views FROM candidates WHERE uri='https://a/1'"
            ).fetchone()
            weight = connection.execute(
                "SELECT weight FROM tag_profile WHERE tag='anime'"
            ).fetchone()[0]
        self.assertAlmostEqual(score, .9)
        self.assertEqual(views, 1)
        self.assertGreater(weight, 0)

    def test_empty_source_selection_returns_nothing(self):
        self.assertEqual(self.engine.recommend(enabled_sources=[]), [])

    def test_browser_page_can_be_liked_and_added_to_profile(self):
        self.engine.like("https://new.example/blue-space", "Blue Space Wallpaper")
        self.assertEqual(self.engine.sources()["new.example"], 1)
        match = [item for item in self.engine.recommend(
            limit=4, enabled_sources=["new.example"]
        ) if item.uri == "https://new.example/blue-space"]
        self.assertEqual(match[0].source, "new.example")
        self.assertGreater(match[0].rating, 3)


if __name__ == "__main__":
    unittest.main()
