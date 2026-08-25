import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "mpvpaper-enginectl.py"
SPEC = importlib.util.spec_from_file_location("mpvpaper_enginectl", MODULE_PATH)
CONTROLLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTROLLER)


class FakeSocket:
    def __init__(self, responses, payloads):
        self.responses = responses
        self.payloads = payloads

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def settimeout(self, _timeout):
        pass

    def connect(self, path):
        self.path = path

    def sendall(self, payload):
        self.payloads.append(json.loads(payload))

    def makefile(self, _mode):
        return self

    def readline(self):
        return self.responses.pop(0)


class ColorEngineTests(unittest.TestCase):
    def test_mpv_options_include_per_output_ipc_and_colors(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(CONTROLLER, "RUNTIME_DIR", Path(directory)):
                config = {
                    **CONTROLLER.DEFAULT_CONFIG,
                    "output": "HDMI-A-1",
                    "brightness": 12,
                    "temperature": 4500,
                    "red_balance": 25,
                    "blue_balance": -8,
                }
                options = CONTROLLER.mpv_options(config)

        self.assertIn("input-ipc-server=", options)
        self.assertIn("HDMI-A-1.sock", options)
        self.assertIn("brightness=12", options)
        self.assertIn("colortemperature=temperature=4500", options)
        self.assertIn("rm=0.25", options)
        self.assertIn("bm=-0.08", options)

    def test_apply_colors_uses_live_mpv_ipc(self):
        payloads = []
        responses = [b'{"error":"success"}\n'] * 6
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            (runtime / "DP-1.sock").touch()
            fake = FakeSocket(responses, payloads)
            with mock.patch.object(CONTROLLER, "RUNTIME_DIR", runtime), mock.patch.object(
                CONTROLLER.socket, "socket", return_value=fake
            ):
                CONTROLLER.apply_colors({
                    **CONTROLLER.DEFAULT_CONFIG,
                    "output": "DP-1",
                    "contrast": 18,
                })

        self.assertEqual(payloads[1]["command"], ["set_property", "contrast", 18])
        self.assertEqual(payloads[-1]["command"][0:2], ["set_property", "vf"])
        self.assertIsInstance(fake.path, str)


if __name__ == "__main__":
    unittest.main()
