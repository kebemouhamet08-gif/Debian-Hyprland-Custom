from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.systemd import (  # noqa: E402
    SystemdError,
    SystemdManager,
    unit_for_output,
)


class RecordingRunner:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.calls = []
        self.result = subprocess.CompletedProcess([], returncode, stdout, stderr)

    def __call__(self, command, **options):
        self.calls.append((command, options))
        return self.result


class SystemdTests(unittest.TestCase):
    def test_unit_names_are_stable(self):
        self.assertEqual(unit_for_output("*"), "mpvpaper-engine-wallpaper-all.service")
        self.assertEqual(unit_for_output("HDMI-A-1"), "mpvpaper-engine-wallpaper-HDMI-A-1.service")

    def test_invalid_output_is_rejected(self):
        with self.assertRaises(ValueError):
            unit_for_output("../../unsafe")

    def test_start_preserves_transient_unit_strategy(self):
        runner = RecordingRunner()
        manager = SystemdManager(runner)
        with tempfile.TemporaryDirectory() as directory:
            wallpaper = Path(directory) / "wall.mp4"
            wallpaper.write_bytes(b"video")
            with mock.patch("mpvpaper_engine.systemd.shutil.which", return_value="/usr/bin/mpvpaper"):
                manager.start_output("eDP-1", wallpaper, "loop-file=inf")
        command = runner.calls[0][0]
        self.assertEqual(command[:4], ["systemd-run", "--user", "--quiet", "--collect"])
        self.assertIn("--unit=mpvpaper-engine-wallpaper-eDP-1.service", command)
        self.assertIn("--auto-pause", command)

    def test_start_can_disable_auto_pause(self):
        runner = RecordingRunner()
        manager = SystemdManager(runner)
        with tempfile.TemporaryDirectory() as directory:
            wallpaper = Path(directory) / "wall.png"
            wallpaper.write_bytes(b"image")
            with mock.patch("mpvpaper_engine.systemd.shutil.which", return_value="mpvpaper"):
                manager.start_output("DP-1", wallpaper, "keep-open=yes", auto_pause=False)
        self.assertNotIn("--auto-pause", runner.calls[0][0])

    def test_missing_mpvpaper_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            wallpaper = Path(directory) / "wall.mp4"
            wallpaper.touch()
            with mock.patch("mpvpaper_engine.systemd.shutil.which", return_value=None):
                with self.assertRaises(SystemdError):
                    SystemdManager(RecordingRunner()).start_output("DP-1", wallpaper, "")

    def test_stop_and_restart_target_only_requested_output(self):
        runner = RecordingRunner()
        manager = SystemdManager(runner)
        manager.stop_output("DP-1")
        manager.restart_output("DP-1")
        self.assertEqual(runner.calls[0][0][2], "stop")
        self.assertEqual(runner.calls[1][0][2], "restart")
        self.assertTrue(all("DP-1.service" in call[0][-1] for call in runner.calls))

    def test_unit_status_is_normalized(self):
        self.assertEqual(SystemdManager(RecordingRunner(stdout="active\n")).unit_status("DP-1"), "active")
        self.assertEqual(SystemdManager(RecordingRunner(stdout="surprise\n")).unit_status("DP-1"), "unknown")

    def test_failed_checked_command_raises(self):
        runner = RecordingRunner(returncode=1, stderr="failed")
        with self.assertRaises(SystemdError):
            SystemdManager(runner).restart_output("DP-1")


if __name__ == "__main__":
    unittest.main()
