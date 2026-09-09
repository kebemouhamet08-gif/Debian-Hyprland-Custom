from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.discovery_download import DiscoveryDownloader  # noqa: E402


class DiscoveryDownloadTests(unittest.TestCase):
    def test_youtube_uses_the_original_known_working_strategy(self):
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch("shutil.which", return_value="/bin/yt-dlp"), \
                mock.patch("subprocess.run", return_value=subprocess.CompletedProcess(
                    [], 1, stdout="", stderr="test failure"
                )) as run:
            downloader = DiscoveryDownloader(Path(directory))
            downloader._yt_dlp(
                "https://www.youtube.com/watch?v=MtJTIuCKzLc", "Video", 1080
            )
        command = run.call_args.args[0]
        self.assertNotIn("--ignore-config", command)
        self.assertNotIn("--extractor-args", command)
        self.assertIn("bv*[height<=1080]+ba/b[height<=1080]", command)


if __name__ == "__main__":
    unittest.main()
