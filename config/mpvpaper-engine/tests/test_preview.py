from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest import mock


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.paths import EnginePaths  # noqa: E402
from mpvpaper_engine.playback import PlaybackError  # noqa: E402
from mpvpaper_engine.preview import (  # noqa: E402
    PreviewCapabilities,
    PreviewSession,
    probe_preview_backends,
)


def temporary_paths(root):
    root = Path(root)
    return EnginePaths.from_environment({
        "HOME": str(root / "home"), "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"), "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_RUNTIME_DIR": str(root / "runtime"),
    })


class FakeProcess:
    def __init__(self, running=True):
        self.running = running
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if self.running else 1

    def terminate(self):
        self.terminated = True
        self.running = False

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True
        self.running = False


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.paths = temporary_paths(self.temporary.name)
        self.media = Path(self.temporary.name) / "preview.mp4"
        self.media.write_bytes(b"video")

    def tearDown(self):
        self.temporary.cleanup()

    def test_backend_probe_marks_libmpv_experimental(self):
        capabilities = probe_preview_backends(
            find_library=lambda name: "libmpv.so.2",
            which=lambda name: "/usr/bin/mpv",
        )
        self.assertEqual(capabilities.recommended, "subprocess")
        self.assertIn("experimental", capabilities.libmpv_status)

    def test_static_fallback_needs_no_process(self):
        session = PreviewSession(
            self.paths,
            capabilities=PreviewCapabilities(None, None, "static"),
        )
        self.assertEqual(session.start(self.media), "static")
        self.assertIsNone(session.process)
        self.assertEqual(session.path, self.media.resolve())

    def test_missing_media_is_rejected(self):
        with self.assertRaises(ValueError):
            PreviewSession(self.paths).start(Path(self.temporary.name) / "missing.mp4")

    def test_subprocess_preview_uses_private_separate_socket(self):
        sockets = []
        commands = []

        def popen(command, **_options):
            commands.append(command)
            socket_argument = next(item for item in command if item.startswith("--input-ipc-server="))
            path = Path(socket_argument.split("=", 1)[1])
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(path))
            sockets.append(server)
            return FakeProcess()

        session = PreviewSession(
            self.paths, popen=popen,
            capabilities=PreviewCapabilities(None, "/usr/bin/mpv", "subprocess"),
        )
        try:
            self.assertEqual(session.start(self.media), "subprocess")
            self.assertIn("preview-", session.socket_path.name)
            self.assertNotEqual(session.socket_path, self.paths.engine_socket)
            self.assertIn("--mute=yes", commands[0])
        finally:
            session.close()
            for server in sockets:
                server.close()

    def test_failed_process_falls_back_to_static(self):
        session = PreviewSession(
            self.paths, popen=lambda *args, **kwargs: FakeProcess(running=False),
            capabilities=PreviewCapabilities(None, "/usr/bin/mpv", "subprocess"),
        )
        self.assertEqual(session.start(self.media), "static")

    def test_controls_use_preview_ipc_only(self):
        session = PreviewSession(self.paths)
        session.backend = "subprocess"
        session.socket_path = self.paths.runtime_home / "preview.sock"
        client = mock.Mock()
        with mock.patch.object(session, "_client", return_value=client):
            session.pause()
            session.play()
            session.seek(3)
            session.mute(True)
            session.restart()
        client.set_property.assert_any_call("pause", True)
        client.set_property.assert_any_call("mute", True)
        client.seek.assert_any_call(3.0, "absolute")
        client.seek.assert_any_call(0.0, "absolute")

    def test_static_preview_rejects_interactive_control(self):
        with self.assertRaises(PlaybackError):
            PreviewSession(self.paths).pause()

    def test_close_terminates_only_owned_preview_process(self):
        process = FakeProcess()
        session = PreviewSession(self.paths)
        session.process = process
        session.close()
        self.assertTrue(process.terminated)
        self.assertIsNone(session.process)


if __name__ == "__main__":
    unittest.main()
