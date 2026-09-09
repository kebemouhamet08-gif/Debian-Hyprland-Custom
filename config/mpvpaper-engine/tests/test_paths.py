import importlib
from pathlib import Path
import sys
import tempfile
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
paths_module = importlib.import_module("mpvpaper_engine.paths")
EnginePaths = paths_module.EnginePaths


class EnginePathsTests(unittest.TestCase):
    def test_custom_xdg_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = EnginePaths.from_environment({
                "HOME": str(root / "home"),
                "XDG_CONFIG_HOME": str(root / "configuration"),
                "XDG_DATA_HOME": str(root / "data"),
                "XDG_CACHE_HOME": str(root / "cache"),
                "XDG_RUNTIME_DIR": str(root / "runtime"),
            })

            self.assertEqual(paths.config_file, root / "configuration/mpvpaper-engine/config.json")
            self.assertEqual(paths.library_db, root / "data/mpvpaper-engine/library.db")
            self.assertEqual(paths.log_dir, root / "cache/mpvpaper-engine/logs")
            self.assertEqual(paths.state_file, root / "runtime/mpvpaper-engine/state.json")

    def test_fallback_paths(self):
        home = Path("/example/home")
        paths = EnginePaths.from_environment({}, home=home, uid=4242)

        self.assertEqual(paths.config_home, home / ".config/mpvpaper-engine")
        self.assertEqual(paths.data_home, home / ".local/share/mpvpaper-engine")
        self.assertEqual(paths.cache_home, home / ".cache/mpvpaper-engine")
        self.assertEqual(paths.runtime_home, Path("/tmp/mpvpaper-engine-4242/mpvpaper-engine"))

    def test_construction_does_not_create_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = EnginePaths.from_environment({
                "HOME": str(root / "home"),
                "XDG_CONFIG_HOME": str(root / "missing-config"),
                "XDG_DATA_HOME": str(root / "missing-data"),
                "XDG_CACHE_HOME": str(root / "missing-cache"),
                "XDG_RUNTIME_DIR": str(root / "missing-runtime"),
            })

            self.assertFalse(paths.config_home.exists())
            self.assertFalse(paths.data_home.exists())
            self.assertFalse(paths.cache_home.exists())
            self.assertFalse(paths.runtime_home.exists())

    def test_socket_names_are_deterministic_and_confined(self):
        paths = EnginePaths.from_environment({}, home=Path("/home/test"), uid=1000)

        self.assertEqual(paths.mpv_socket("*"), paths.mpv_socket_dir / "all.sock")
        self.assertEqual(
            paths.mpv_socket("HDMI-A-1"), paths.mpv_socket_dir / "HDMI-A-1.sock"
        )
        self.assertEqual(
            paths.mpv_socket("unsafe/output"), paths.mpv_socket_dir / "unsafe-output.sock"
        )


if __name__ == "__main__":
    unittest.main()
