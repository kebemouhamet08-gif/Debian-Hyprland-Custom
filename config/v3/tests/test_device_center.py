import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "device-center.py"
SPEC = importlib.util.spec_from_file_location("device_center", MODULE_PATH)
DEVICE_CENTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEVICE_CENTER)


class DeviceCenterTests(unittest.TestCase):
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
