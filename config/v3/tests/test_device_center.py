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

    def test_keyboard_reports_are_rendered_as_named_keys(self):
        report = {"raw_hex": "00001a0000000000", "report_id": None}
        self.assertEqual(DEVICE_CENTER.keyboard_report_keys(report), {"W"})
        self.assertEqual(
            DEVICE_CENTER.summarize_hid_report("keyboard", report), "Touches : W"
        )

    def test_mouse_reports_render_buttons_movement_and_wheel(self):
        report = {"raw_hex": "010105ff01", "report_id": 1}
        summary = DEVICE_CENTER.summarize_hid_report("mouse", report)
        self.assertIn("Boutons : 1", summary)
        self.assertIn("X +5", summary)
        self.assertIn("Y -1", summary)
        self.assertIn("molette +1", summary)

    def test_linux_input_events_cover_keyboard_mouse_and_gamepad(self):
        self.assertEqual(
            DEVICE_CENTER.decode_input_event({"type": 1, "code": 17, "value": 1}),
            "Z · pressé",
        )
        self.assertEqual(
            DEVICE_CENTER.decode_input_event({"type": 2, "code": 0, "value": -4}),
            "X · -4",
        )
        self.assertEqual(
            DEVICE_CENTER.decode_input_event({"type": 3, "code": 16, "value": 1}),
            "Croix X · 1",
        )

    def test_only_event_nodes_are_used_for_live_input(self):
        device = {"nodes": ["/dev/hidraw1", "/dev/input/event20", "/dev/input/mouse4"]}
        self.assertEqual(DEVICE_CENTER.event_nodes(device), ["/dev/input/event20"])


if __name__ == "__main__":
    unittest.main()
