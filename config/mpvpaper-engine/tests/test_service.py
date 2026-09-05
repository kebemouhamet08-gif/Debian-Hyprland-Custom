import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest import mock


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.ipc import (  # noqa: E402
    EngineAlreadyRunningError,
    EngineClient,
    EngineProtocolError,
)
from mpvpaper_engine.paths import EnginePaths  # noqa: E402
from mpvpaper_engine.service import EngineService  # noqa: E402
from mpvpaper_engine.state import read_state  # noqa: E402


def temporary_paths(root):
    root = Path(root)
    return EnginePaths.from_environment({
        "HOME": str(root / "home"), "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"), "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_RUNTIME_DIR": str(root / "runtime"),
    })


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.paths = temporary_paths(self.temporary.name)
        self.paths.config_home.mkdir(parents=True)
        self.paths.config_file.write_text(json.dumps({
            "output": "eDP-1",
            "wallpaper": "/wallpapers/laptop.mp4",
            "volume": 12,
            "assignments": {
                "eDP-1": {"wallpaper": "/wallpapers/laptop.mp4", "volume": 12},
                "HDMI-A-1": {"wallpaper": "/wallpapers/external.png", "volume": 34},
            },
        }), encoding="utf-8")
        self.service = EngineService(self.paths)

    def tearDown(self):
        self.service.shutdown()
        self.temporary.cleanup()

    def test_service_startup(self):
        self.service.start()
        self.assertTrue(self.service.server.running)

    def test_config_is_loaded_without_migration(self):
        before = self.paths.config_file.read_bytes()
        self.assertEqual(set(self.service.config.outputs), {"eDP-1", "HDMI-A-1"})
        self.assertEqual(self.paths.config_file.read_bytes(), before)

    def test_initial_state_is_prudent(self):
        state = self.service.state.snapshot()
        output = state.outputs["eDP-1"]
        self.assertEqual(output.status.value, "stopped")
        self.assertIsNone(output.position)
        self.assertIsNone(output.duration)
        self.assertEqual(str(output.path), "/wallpapers/laptop.mp4")

    def test_ping(self):
        self.service.start()
        self.assertEqual(EngineClient(self.paths).ping(), {"pong": True})

    def test_get_version(self):
        self.service.start()
        version = EngineClient(self.paths).get_version()
        self.assertEqual(version["protocol"], 1)
        self.assertEqual(version["state"], 1)

    def test_list_outputs(self):
        self.service.start()
        self.assertEqual(EngineClient(self.paths).list_outputs(), ["HDMI-A-1", "eDP-1"])

    def test_get_output_state(self):
        self.service.start()
        output = EngineClient(self.paths).get_output_state("HDMI-A-1")
        self.assertEqual(output["path"], "/wallpapers/external.png")
        self.assertEqual(output["volume"], 34)

    def test_unknown_output_returns_error(self):
        self.service.start()
        with self.assertRaises(EngineProtocolError) as caught:
            EngineClient(self.paths).get_output_state("DP-9")
        self.assertEqual(caught.exception.code, "output_not_found")

    def test_state_file_created_with_running_status(self):
        self.service.start()
        self.assertEqual(read_state(self.paths).service_status, "running")

    def test_start_reconstructs_preexisting_wallpaper_once(self):
        self.paths.mpv_socket_dir.mkdir(parents=True)
        existing = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        existing.bind(str(self.paths.mpv_socket("eDP-1")))
        self.service.playback.get_state = mock.Mock()
        try:
            self.service.start()
            self.service.playback.get_state.assert_called_once_with("eDP-1")
        finally:
            existing.close()

    def test_single_instance(self):
        self.service.start()
        second = EngineService(self.paths)
        with self.assertRaises(EngineAlreadyRunningError):
            second.start()
        second.shutdown()

    def test_request_shutdown_sets_event_without_signal(self):
        self.service.request_shutdown()
        self.assertTrue(self.service._stop_event.is_set())

    def test_shutdown_removes_socket_and_keeps_stopped_snapshot(self):
        self.service.start()
        self.service.shutdown()
        self.assertFalse(self.paths.engine_socket.exists())
        self.assertEqual(read_state(self.paths).service_status, "stopped")

    def test_playback_pause_and_seek_are_dispatched(self):
        self.service.playback.pause = mock.Mock()
        self.service.playback.seek = mock.Mock()
        self.service.start()
        client = EngineClient(self.paths)
        self.assertEqual(client.pause("eDP-1"), {"paused": True})
        self.assertEqual(client.seek("eDP-1", 8.5), {"position": 8.5})
        self.service.playback.pause.assert_called_once_with("eDP-1")
        self.service.playback.seek.assert_called_once_with("eDP-1", 8.5)

    def test_playback_live_settings_are_dispatched(self):
        self.service.playback.set_volume = mock.Mock(return_value=100)
        self.service.playback.set_speed = mock.Mock(return_value=0.5)
        self.service.start()
        client = EngineClient(self.paths)
        self.assertEqual(client.set_volume("eDP-1", 200), {"volume": 100})
        self.assertEqual(client.set_speed("eDP-1", 0.5), {"speed": 0.5})

    def test_playback_invalid_parameters_are_structured_errors(self):
        self.service.start()
        with self.assertRaises(EngineProtocolError) as caught:
            EngineClient(self.paths).request("set_mute", {
                "output": "eDP-1", "muted": "false",
            })
        self.assertEqual(caught.exception.code, "playback_error")


if __name__ == "__main__":
    unittest.main()
