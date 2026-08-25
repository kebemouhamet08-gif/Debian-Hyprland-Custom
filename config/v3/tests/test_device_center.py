import importlib.util
import pathlib
import subprocess
import unittest
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).parents[1] / "device-center.py"
SPEC = importlib.util.spec_from_file_location("device_center", MODULE_PATH)
DEVICE_CENTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEVICE_CENTER)


class DeviceCenterTests(unittest.TestCase):
    def test_cli_command_uses_the_python_interpreter_for_local_source(self):
        command = DEVICE_CENTER.periphx_cli_command()
        self.assertEqual(command[0], DEVICE_CENTER.sys.executable)
        self.assertEqual(pathlib.Path(command[1]).name, "periphx.py")

    def test_driver_cli_uses_read_only_manifest_commands(self):
        completed = subprocess.CompletedProcess(
            ["periphx-cli"], 0,
            stdout='[{"name":"mouse-driver","valid":true}]', stderr="",
        )
        with mock.patch.object(DEVICE_CENTER, "periphx_cli_command", return_value=["periphx-cli"]), \
                mock.patch.object(DEVICE_CENTER.subprocess, "run", return_value=completed) as runner:
            manifests = DEVICE_CENTER.driver_cli_json("list")
        self.assertEqual(manifests[0]["name"], "mouse-driver")
        self.assertEqual(runner.call_args.args[0], ["periphx-cli", "drivers", "list"])

    def test_capture_cli_targets_one_selected_interface(self):
        completed = subprocess.CompletedProcess(
            ["periphx-cli"], 0, stdout='{"reports":[],"safety":"read-only"}', stderr="",
        )
        with mock.patch.object(DEVICE_CENTER, "periphx_cli_command", return_value=["periphx-cli"]), \
                mock.patch.object(DEVICE_CENTER.subprocess, "run", return_value=completed) as runner:
            result = DEVICE_CENTER.periphx_cli_json(
                "capture", "device-1", "--interface", "interface-2", "--json"
            )
        self.assertEqual(result["safety"], "read-only")
        self.assertEqual(
            runner.call_args.args[0],
            ["periphx-cli", "capture", "device-1", "--interface", "interface-2", "--json"],
        )

    def test_internal_keyboard_is_not_managed(self):
        self.assertFalse(DEVICE_CENTER.is_external_peripheral({
            "class": "keyboard",
            "classes": ["keyboard"],
            "external": False,
            "connection": "i8042",
        }))

    def test_composite_external_device_gets_each_interface(self):
        device = {
            "id": "usb:1234:5678:receiver",
            "class": "keyboard",
            "classes": ["keyboard", "mouse"],
            "external": True,
            "connection": "usb",
            "name": "Combo Receiver",
            "capabilities": ["keyboard.buttons", "mouse.buttons"],
        }
        groups = DEVICE_CENTER.daemon_device_groups([device])
        by_title = {title: items for title, _subtitle, items, _kind in groups}
        self.assertEqual(by_title["Claviers"][0]["class"], "keyboard")
        self.assertEqual(by_title["Souris"][0]["class"], "mouse")
        self.assertEqual(by_title["Manettes"], [])


if __name__ == "__main__":
    unittest.main()
