import contextlib
import importlib.util
import io
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "periphx.py"
SPEC = importlib.util.spec_from_file_location("periphx_cli", MODULE_PATH)
PERIPHX = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PERIPHX)


class PeriphxCliTests(unittest.TestCase):
    def test_inspect_supports_nested_descriptor_schema(self):
        result = {
            "device": {
                "name": "Test Mouse",
                "vendor_id": "1234",
                "product_id": "5678",
                "driver": "generic-hid",
                "nodes": ["/dev/hidraw3"],
            },
            "hid": {
                "descriptor": {
                    "usage_pages": [{"id": 1, "name": "Generic Desktop"}]
                },
                "nodes": ["/dev/hidraw3"],
                "writable_protocol": "unknown",
            },
            "safety": "read-only",
        }
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            PERIPHX.print_inspection(result)
        rendered = output.getvalue()
        self.assertIn("Test Mouse", rendered)
        self.assertIn("Generic Desktop", rendered)
        self.assertIn("/dev/hidraw3", rendered)

    def test_inspect_keeps_legacy_flat_schema(self):
        result = {
            "device": {"name": "Legacy", "driver": "generic-hid"},
            "hid": {
                "nodes": ["/dev/hidraw1"],
                "usage_pages": ["Button"],
                "writable_protocol": "unknown",
            },
        }
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            PERIPHX.print_inspection(result)
        self.assertIn("Button", output.getvalue())

    def test_interfaces_render_selected_hid_nodes(self):
        result = {
            "interfaces": [
                {
                    "id": "path:1234:5678:usb-1",
                    "name": "Interface 01",
                    "role": "mouse",
                    "risk": "standard-read-only",
                    "nodes": ["/dev/hidraw2"],
                    "descriptor_size": 64,
                }
            ]
        }
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            PERIPHX.print_interfaces(result)
        rendered = output.getvalue()
        self.assertIn("Interface 01", rendered)
        self.assertIn("/dev/hidraw2", rendered)
        self.assertIn("64 bytes", rendered)


if __name__ == "__main__":
    unittest.main()
