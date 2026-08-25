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
    def test_malformed_config_is_normalized_without_crashing(self):
        malformed = {
            "wallpaper": ["not-a-path"],
            "output": "../../unsafe-output",
            "volume": "invalide",
            "speed": float("inf"),
            "gamma": 900,
            "temperature": "500",
            "assignments": {"DP-1": {"contrast": "bad"}, "": {}},
        }
        with tempfile.TemporaryDirectory() as directory:
            config_file = Path(directory) / "config.json"
            config_file.write_text(json.dumps(malformed), encoding="utf-8")
            with mock.patch.object(CONTROLLER, "CONFIG_FILE", config_file):
                config = CONTROLLER.load_config()

        self.assertEqual(config["wallpaper"], "")
        self.assertEqual(config["output"], "*")
        self.assertEqual(config["volume"], 0)
        self.assertEqual(config["speed"], 5.0)
        self.assertEqual(config["gamma"], 100)
        self.assertEqual(config["temperature"], 1000)
        self.assertEqual(set(config["assignments"]), {"DP-1"})

    def test_save_config_is_private_and_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            config_dir = Path(directory) / "config"
            config_file = config_dir / "config.json"
            with mock.patch.object(CONTROLLER, "CONFIG_DIR", config_dir), mock.patch.object(
                CONTROLLER, "CONFIG_FILE", config_file
            ):
                CONTROLLER.save_config(CONTROLLER.DEFAULT_CONFIG)
            self.assertEqual(config_dir.stat().st_mode & 0o777, 0o700)
            self.assertEqual(config_file.stat().st_mode & 0o777, 0o600)

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
