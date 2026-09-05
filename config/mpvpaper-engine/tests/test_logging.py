import importlib
import io
from logging import DEBUG, WARNING, StreamHandler
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
logging_module = importlib.import_module("mpvpaper_engine.logging")
paths_module = importlib.import_module("mpvpaper_engine.paths")
EnginePaths = paths_module.EnginePaths


def close_handlers(logger):
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


class LoggingTests(unittest.TestCase):
    def paths_for(self, root):
        return EnginePaths.from_environment({
            "HOME": str(root / "home"),
            "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_DATA_HOME": str(root / "data"),
            "XDG_CACHE_HOME": str(root / "cache"),
            "XDG_RUNTIME_DIR": str(root / "runtime"),
        })

    def test_normal_and_debug_levels(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.paths_for(Path(directory))
            normal = logging_module.configure_logging(
                paths, {}, logger_name="mpvpaper_engine.test.normal"
            )
            debug = logging_module.configure_logging(
                paths, {"MPVPAPER_ENGINE_DEBUG": "1"},
                logger_name="mpvpaper_engine.test.debug",
            )
            try:
                self.assertEqual(normal.level, WARNING)
                self.assertEqual(debug.level, DEBUG)
            finally:
                close_handlers(normal)
                close_handlers(debug)

    def test_rotating_file_configuration_uses_custom_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.paths_for(Path(directory))
            logger = logging_module.configure_logging(
                paths, {}, logger_name="mpvpaper_engine.test.rotation"
            )
            try:
                handler = logger.handlers[0]
                self.assertIsInstance(handler, RotatingFileHandler)
                self.assertEqual(handler.maxBytes, 5 * 1024 * 1024)
                self.assertEqual(handler.backupCount, 3)
                self.assertEqual(Path(handler.baseFilename).parent, paths.log_dir)
            finally:
                close_handlers(logger)

    def test_logging_falls_back_to_stream(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.paths_for(Path(directory))
            stream = io.StringIO()
            with mock.patch.object(Path, "mkdir", side_effect=OSError("read-only")):
                logger = logging_module.configure_logging(
                    paths, {}, logger_name="mpvpaper_engine.test.fallback", stream=stream
                )
            try:
                self.assertIsInstance(logger.handlers[0], StreamHandler)
                self.assertNotIsInstance(logger.handlers[0], RotatingFileHandler)
                logger.warning("fallback works")
                self.assertIn("fallback works", stream.getvalue())
            finally:
                close_handlers(logger)


if __name__ == "__main__":
    unittest.main()
