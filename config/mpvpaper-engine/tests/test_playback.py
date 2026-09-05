import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.config import normalize_v2_config  # noqa: E402
from mpvpaper_engine.models import ColorProfile, PlaybackStatus  # noqa: E402
from mpvpaper_engine.paths import EnginePaths  # noqa: E402
from mpvpaper_engine.playback import (  # noqa: E402
    MpvClient,
    MpvUnavailableError,
    PlaybackError,
    PlaybackController,
    _wait_for_media_path,
    color_filter,
    mpv_socket_candidates,
)


def temporary_paths(root):
    root = Path(root)
    return EnginePaths.from_environment({
        "HOME": str(root / "home"), "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"), "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_RUNTIME_DIR": str(root / "runtime"),
    })


class FakeMpv:
    def __init__(self, properties=None, unavailable=False):
        self.properties = dict(properties or {})
        self.commands = []
        self.unavailable = unavailable

    def loadfile(self, path):
        if self.unavailable:
            raise MpvUnavailableError("missing")
        self.commands.append(("loadfile", str(path), "replace"))
        self.properties["path"] = str(path)

    def set_property(self, name, value):
        self.commands.append(("set_property", name, value))
        self.properties[name] = value

    def get_property(self, name):
        self.commands.append(("get_property", name))
        return self.properties.get(name)

    def seek(self, value, mode):
        self.commands.append(("seek", value, mode))


class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.paths = temporary_paths(self.temporary.name)
        self.config = normalize_v2_config({
            "schema_version": 2,
            "defaults": {"volume": 15, "muted": False, "speed": 1.25},
            "outputs": {"DP-1": {"fit_mode": "contain", "contrast": 4}},
        })
        self.systemd = mock.Mock()
        self.controller = PlaybackController(
            self.config, self.paths, systemd=self.systemd
        )
        self.wallpaper = Path(self.temporary.name) / "wall.mp4"
        self.wallpaper.write_bytes(b"video")

    def tearDown(self):
        self.temporary.cleanup()

    def test_mpv_client_json_protocol(self):
        self.paths.runtime_home.mkdir(parents=True)
        path = self.paths.runtime_home / "fake.sock"
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path))
        server.listen(1)
        received = []

        def respond():
            connection, _ = server.accept()
            with connection:
                request = json.loads(connection.makefile("rb").readline())
                received.append(request)
                connection.sendall(json.dumps({
                    "request_id": request["request_id"], "error": "success", "data": 1.5,
                }).encode() + b"\n")
            server.close()

        thread = threading.Thread(target=respond)
        thread.start()
        self.assertEqual(MpvClient(path).get_property("speed"), 1.5)
        thread.join()
        self.assertEqual(received[0]["command"], ["get_property", "speed"])

    def test_socket_candidates_include_new_and_legacy_locations(self):
        candidates = mpv_socket_candidates(self.paths, "DP-1")
        self.assertEqual(candidates[0], self.paths.mpv_socket("DP-1"))
        self.assertEqual(candidates[1], self.paths.runtime_home / "DP-1.sock")

    def test_play_uses_loadfile_without_restart_when_socket_works(self):
        mpv = FakeMpv()
        with mock.patch.object(self.controller, "_client", return_value=mpv):
            strategy = self.controller.play("DP-1", self.wallpaper)
        self.assertEqual(strategy, "loadfile")
        self.assertEqual(mpv.commands[0], ("loadfile", str(self.wallpaper), "replace"))
        self.systemd.start_output.assert_not_called()
        self.assertIn(("set_property", "contrast", 4), mpv.commands)

    def test_generated_service_options_disable_terminal_spam(self):
        options = self.controller._mpv_options("DP-1", self.controller._profile("DP-1"))
        self.assertIn("terminal=no", options)

    def test_play_falls_back_to_transient_systemd(self):
        with mock.patch.object(
            self.controller, "_client", return_value=FakeMpv(unavailable=True)
        ):
            strategy = self.controller.play("DP-1", self.wallpaper)
        self.assertEqual(strategy, "systemd")
        self.systemd.stop_output.assert_called_once_with("DP-1")
        self.systemd.start_output.assert_called_once()

    def test_missing_or_unsupported_wallpaper_is_rejected(self):
        with self.assertRaises(ValueError):
            self.controller.play("DP-1", Path(self.temporary.name) / "missing.mp4")
        invalid = Path(self.temporary.name) / "wall.txt"
        invalid.touch()
        with self.assertRaises(ValueError):
            self.controller.play("DP-1", invalid)

    def test_pause_resume_and_toggle_are_live(self):
        mpv = FakeMpv({"pause": False})
        with mock.patch.object(self.controller, "_client", return_value=mpv):
            self.controller.pause("DP-1")
            self.controller.resume("DP-1")
            self.assertTrue(self.controller.toggle_pause("DP-1"))
        self.assertIn(("set_property", "pause", True), mpv.commands)
        self.assertIn(("set_property", "pause", False), mpv.commands)

    def test_absolute_and_relative_seek(self):
        mpv = FakeMpv()
        with mock.patch.object(self.controller, "_client", return_value=mpv):
            self.controller.seek("DP-1", 12.5)
            self.controller.seek_relative("DP-1", -3)
        self.assertIn(("seek", 12.5, "absolute"), mpv.commands)
        self.assertIn(("seek", -3.0, "relative"), mpv.commands)
        with self.assertRaises(ValueError):
            self.controller.seek("DP-1", -1)

    def test_volume_and_speed_are_bounded(self):
        mpv = FakeMpv()
        with mock.patch.object(self.controller, "_client", return_value=mpv):
            self.assertEqual(self.controller.set_volume("DP-1", 200), 100)
            self.assertEqual(self.controller.set_speed("DP-1", 0), 0.1)

    def test_mute_and_loop_require_real_booleans(self):
        mpv = FakeMpv()
        with mock.patch.object(self.controller, "_client", return_value=mpv):
            self.controller.set_mute("DP-1", True)
            self.controller.set_loop("DP-1", False)
            with self.assertRaises(ValueError):
                self.controller.set_mute("DP-1", "false")
        self.assertIn(("set_property", "loop-file", "no"), mpv.commands)

    def test_fit_modes_apply_live_properties(self):
        mpv = FakeMpv()
        with mock.patch.object(self.controller, "_client", return_value=mpv):
            self.controller.set_fit("DP-1", "stretch")
            with self.assertRaises(ValueError):
                self.controller.set_fit("DP-1", "crop-random")
        self.assertIn(("set_property", "keepaspect", False), mpv.commands)

    def test_color_profile_applies_all_live_properties(self):
        mpv = FakeMpv()
        profile = ColorProfile(name="Cinema", contrast=12, temperature=5000, red_balance=8)
        with mock.patch.object(self.controller, "_client", return_value=mpv):
            self.controller.set_color("DP-1", profile)
        self.assertIn(("set_property", "contrast", 12), mpv.commands)
        vf = next(item[2] for item in mpv.commands if item[1] == "vf")
        self.assertIn("temperature=5000", vf)
        self.assertIn("rm=0.08", vf)

    def test_get_state_reads_only_known_mpv_properties(self):
        mpv = FakeMpv({
            "path": "/wall/current.mp4", "pause": True, "time-pos": 9.0,
            "duration": 40.0, "volume": 22, "mute": False, "speed": 1.1,
        })
        with mock.patch.object(self.controller, "_client", return_value=mpv):
            state = self.controller.get_state("DP-1")
        self.assertEqual(state.status, PlaybackStatus.PAUSED)
        self.assertEqual(state.path, Path("/wall/current.mp4"))
        self.assertEqual(state.position, 9.0)

    def test_stop_and_restart_use_systemd_abstraction(self):
        self.controller.stop("DP-1")
        self.controller.restart("DP-1")
        self.systemd.stop_output.assert_called_once_with("DP-1")
        self.systemd.restart_output.assert_called_once_with("DP-1")

    def test_color_filter_bounds_temperature_and_rgb(self):
        value = color_filter({"temperature": 99999, "red_balance": 500})
        self.assertIn("temperature=40000", value)
        self.assertIn("rm=1.00", value)

    def test_performance_profile_restarts_target_with_new_options(self):
        state = mock.Mock()
        state.snapshot.return_value = SimpleNamespace(
            outputs={"DP-1": SimpleNamespace(path=self.wallpaper)}
        )
        controller = PlaybackController(
            self.config, self.paths, state=state, systemd=self.systemd
        )
        self.assertEqual(controller.set_performance_profile("DP-1", "eco"), "eco")
        self.systemd.stop_output.assert_called_once_with("DP-1")
        options = self.systemd.start_output.call_args.args[2]
        self.assertIn("vf-add=fps=fps=24", options)
        self.assertIn("vf-add=scale=-2:720", options)
        state.update_output.assert_called_with(
            "DP-1", performance_profile=mock.ANY
        )

    def test_performance_profile_rejects_unknown_mode(self):
        with self.assertRaisesRegex(ValueError, "invalid performance"):
            self.controller.set_performance_profile("DP-1", "turbo")


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.now += duration


class PathSequenceClient:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0

    def get_property(self, name):
        self.calls += 1
        value = self.values.pop(0) if len(self.values) > 1 else self.values[0]
        if isinstance(value, Exception):
            raise value
        return value


class LoadfileWaitTests(unittest.TestCase):
    def wait(self, values, expected=Path("/wall/b.mp4"), timeout=1.0):
        clock = FakeClock()
        client = PathSequenceClient(values)
        result = _wait_for_media_path(
            client, expected, timeout=timeout, interval=0.1,
            monotonic=clock.monotonic, sleep=clock.sleep,
        )
        return result, client, clock

    def test_path_available_immediately(self):
        result, client, clock = self.wait(["/wall/b.mp4"])
        self.assertEqual(result, "/wall/b.mp4")
        self.assertEqual(client.calls, 1)
        self.assertEqual(clock.sleeps, [])

    def test_property_unavailable_once_then_success(self):
        result, client, _ = self.wait([
            PlaybackError("property unavailable"), "/wall/b.mp4",
        ])
        self.assertEqual(result, "/wall/b.mp4")
        self.assertEqual(client.calls, 2)

    def test_property_unavailable_multiple_times_then_success(self):
        result, client, _ = self.wait([
            PlaybackError("property unavailable"),
            PlaybackError("property is unavailable"),
            "/wall/b.mp4",
        ])
        self.assertEqual(result, "/wall/b.mp4")
        self.assertEqual(client.calls, 3)

    def test_wrong_path_then_expected_path(self):
        result, client, _ = self.wait(["/wall/a.mp4", "/wall/b.mp4"])
        self.assertEqual(result, "/wall/b.mp4")
        self.assertEqual(client.calls, 2)

    def test_property_unavailable_until_timeout(self):
        clock = FakeClock()
        client = PathSequenceClient([PlaybackError("property unavailable")])
        with self.assertRaisesRegex(PlaybackError, "timed out"):
            _wait_for_media_path(
                client, Path("/wall/b.mp4"), timeout=0.25, interval=0.1,
                monotonic=clock.monotonic, sleep=clock.sleep,
            )
        self.assertGreaterEqual(client.calls, 2)
        self.assertAlmostEqual(clock.now, 0.25)

    def test_non_transient_playback_error_is_immediate(self):
        clock = FakeClock()
        client = PathSequenceClient([PlaybackError("permission denied")])
        with self.assertRaisesRegex(PlaybackError, "permission denied"):
            _wait_for_media_path(
                client, Path("/wall/b.mp4"), timeout=1, interval=0.1,
                monotonic=clock.monotonic, sleep=clock.sleep,
            )
        self.assertEqual(client.calls, 1)
        self.assertEqual(clock.sleeps, [])

    def test_restore_uses_same_transient_tolerance(self):
        restored, client, _ = self.wait([
            PlaybackError("property unavailable"), "/wall/a.mp4",
        ], expected=Path("/wall/a.mp4"))
        self.assertEqual(restored, "/wall/a.mp4")
        self.assertEqual(client.calls, 2)

    def test_equivalent_normalized_paths_match(self):
        result, _, _ = self.wait(
            ["/wall/sub/../b.mp4"], expected=Path("/wall/b.mp4")
        )
        self.assertEqual(result, "/wall/sub/../b.mp4")


if __name__ == "__main__":
    unittest.main()
