from pathlib import Path
from contextlib import closing
import sqlite3
import sys
import tempfile
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.migrations import preserve_recommendations  # noqa: E402


class DataMigrationTests(unittest.TestCase):
    def test_recommendations_are_copied_without_modifying_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "suggestions.db"
            destination = root / "data" / "recommendations.db"
            with closing(sqlite3.connect(source)) as connection, connection:
                connection.execute("CREATE TABLE candidates(uri TEXT)")
                connection.executemany("INSERT INTO candidates VALUES (?)", [("a",), ("b",)])
            before = source.read_bytes()
            result = preserve_recommendations(source, destination)
            self.assertEqual(result, {"copied": True, "candidates": 2})
            self.assertEqual(source.read_bytes(), before)
            with closing(sqlite3.connect(destination)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM candidates").fetchone()[0], 2)

    def test_existing_destination_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / "old.db", root / "new.db"
            source.write_bytes(b"old")
            destination.write_bytes(b"keep")
            self.assertFalse(preserve_recommendations(source, destination)["copied"])
            self.assertEqual(destination.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
