from pathlib import Path
import subprocess
import sys
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.wallpaper_providers import WallpaperProviderManager  # noqa: E402


class WallpaperProviderTests(unittest.TestCase):
    def test_stops_known_providers_and_ignores_absent_processes(self):
        calls = []

        def runner(command, **_options):
            calls.append(command)
            return subprocess.CompletedProcess(command, 1, "", "")

        self.assertEqual(WallpaperProviderManager(runner).stop_conflicting(), [])
        self.assertEqual(calls[0], [
            "pkill", "-f", r"(^|/)WallpaperAutoChange[.]sh( |$)"
        ])
        self.assertEqual(calls[1], ["pkill", "-x", "swww-daemon"])

    def test_reports_stopped_providers(self):
        manager = WallpaperProviderManager(
            lambda command, **_options: subprocess.CompletedProcess(command, 0, "", "")
        )
        self.assertEqual(
            manager.stop_conflicting(),
            ["WallpaperAutoChange.sh", "swww-daemon"],
        )
