import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.ipc import (  # noqa: E402
    EngineAlreadyRunningError,
    EngineClient,
    EngineProtocolError,
    EngineServer,
    MAX_MESSAGE_BYTES,
)
from mpvpaper_engine.paths import EnginePaths  # noqa: E402


def temporary_paths(root):
    root = Path(root)
    return EnginePaths.from_environment({
        "HOME": str(root / "home"), "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"), "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_RUNTIME_DIR": str(root / "runtime"),
    })


def raw_request(path, payload):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(1)
        client.connect(str(path))
        client.sendall(payload)
        return json.loads(client.makefile("rb").readline())


class IPCTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.paths = temporary_paths(self.temporary.name)
        self.server = EngineServer({
            "ping": lambda _params: {"pong": True},
            "get_state": lambda _params: {"service_status": "running"},
            "slow": lambda _params: (time.sleep(0.15) or {"done": True}),
        }, self.paths)

    def tearDown(self):
        self.server.shutdown()
        self.temporary.cleanup()

    def test_ping_over_real_unix_socket(self):
        self.server.start()
        self.assertEqual(EngineClient(self.paths).ping(), {"pong": True})

    def test_get_state(self):
        self.server.start()
        self.assertEqual(EngineClient(self.paths).get_state()["service_status"], "running")

    def test_unknown_method_returns_structured_error(self):
        self.server.start()
        with self.assertRaises(EngineProtocolError) as caught:
            EngineClient(self.paths).request("missing")
        self.assertEqual(caught.exception.code, "unknown_method")

    def test_invalid_json_does_not_stop_server(self):
        self.server.start()
        response = raw_request(self.paths.engine_socket, b"{invalid}\n")
        self.assertEqual(response["error"]["code"], "invalid_json")
        self.assertTrue(EngineClient(self.paths).ping()["pong"])

    def test_invalid_params_are_rejected(self):
        self.server.start()
        response = raw_request(
            self.paths.engine_socket,
            b'{"id":3,"method":"ping","params":[]}\n',
        )
        self.assertEqual(response["error"]["code"], "invalid_params")

    def test_missing_method_is_rejected(self):
        self.server.start()
        response = raw_request(self.paths.engine_socket, b'{"id":4,"params":{}}\n')
        self.assertEqual(response["error"]["code"], "invalid_request")

    def test_invalid_id_and_non_object_request_are_rejected(self):
        self.server.start()
        invalid_id = raw_request(
            self.paths.engine_socket,
            b'{"id":true,"method":"ping","params":{}}\n',
        )
        non_object = raw_request(self.paths.engine_socket, b'[]\n')
        self.assertEqual(invalid_id["error"]["code"], "invalid_request")
        self.assertEqual(non_object["error"]["code"], "invalid_request")

    def test_oversized_message_is_rejected(self):
        self.server.start()
        response = raw_request(self.paths.engine_socket, b"x" * (MAX_MESSAGE_BYTES + 1) + b"\n")
        self.assertEqual(response["error"]["code"], "request_too_large")

    def test_client_timeout_is_bounded(self):
        self.server.start()
        with self.assertRaises(TimeoutError):
            EngineClient(self.paths, timeout=0.02).request("slow")

    def test_socket_and_runtime_permissions(self):
        self.server.start()
        self.assertEqual(self.paths.runtime_home.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.paths.engine_socket.stat().st_mode & 0o777, 0o600)

    def test_stale_socket_is_removed_safely(self):
        self.paths.runtime_home.mkdir(parents=True)
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(str(self.paths.engine_socket))
        stale.close()
        self.server.start()
        self.assertTrue(EngineClient(self.paths).ping()["pong"])

    def test_active_socket_enforces_single_instance(self):
        self.server.start()
        second = EngineServer({}, self.paths)
        with self.assertRaises(EngineAlreadyRunningError):
            second.start()
        second.shutdown()

    def test_client_disconnect_before_newline_is_isolated(self):
        self.server.start()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(self.paths.engine_socket))
            client.sendall(b'{"id":1')
        self.assertTrue(EngineClient(self.paths).ping()["pong"])

    def test_two_clients_can_run_concurrently(self):
        self.server.start()
        results = []
        threads = [threading.Thread(
            target=lambda: results.append(EngineClient(self.paths).ping()["pong"])
        ) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(results, [True, True])

    def test_clean_shutdown_removes_socket(self):
        self.server.start()
        self.server.shutdown()
        self.assertFalse(self.paths.engine_socket.exists())


if __name__ == "__main__":
    unittest.main()
