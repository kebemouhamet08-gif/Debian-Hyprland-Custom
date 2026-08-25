import contextlib
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
from unittest import mock


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

    def test_capture_rendering_preserves_report_id_none(self):
        result = {
            "reports": [
                {
                    "node": "/dev/hidraw2",
                    "size": 2,
                    "report_id": None,
                    "raw_hex": "00ff",
                }
            ]
        }
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            PERIPHX.print_capture(result)
        rendered = output.getvalue()
        self.assertIn("report none", rendered)
        self.assertIn("00ff", rendered)

    def test_custom_driver_install_and_update_are_atomic(self):
        manifest = {
            "schema_version": 1,
            "name": "test-mouse",
            "version": "1.0.0",
            "match": {
                "vendor_id": "1234",
                "product_id": "5678",
                "interface_number": "01",
            },
            "capabilities": ["device.info", "hid.inspect"],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            source = root / "source.json"
            source.write_text(json.dumps(manifest), encoding="utf-8")
            with mock.patch.dict("os.environ", {"XDG_CONFIG_HOME": str(root / "config")}):
                target = PERIPHX.install_driver_manifest(source)
                self.assertTrue(target.is_file())
                self.assertEqual(target.stat().st_mode & 0o777, 0o600)
                manifest["version"] = "1.1.0"
                source.write_text(json.dumps(manifest), encoding="utf-8")
                PERIPHX.install_driver_manifest(source, update=True)
                self.assertEqual(PERIPHX.load_driver_manifest(target)["version"], "1.1.0")

    def test_custom_driver_rejects_writable_capability(self):
        manifest = {
            "schema_version": 1,
            "name": "unsafe-mouse",
            "version": "1.0.0",
            "match": {"vendor_id": "1234", "product_id": "5678"},
            "capabilities": ["mouse.dpi.write"],
        }
        with tempfile.TemporaryDirectory() as temporary:
            source = pathlib.Path(temporary) / "unsafe.json"
            source.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                PERIPHX.load_driver_manifest(source)

    def test_custom_driver_rejects_malformed_types_cleanly(self):
        manifest = {
            "schema_version": True,
            "name": ["not-a-name"],
            "version": "1.0.0",
            "match": {"vendor_id": "1234", "product_id": "5678"},
            "capabilities": [{}],
        }
        with tempfile.TemporaryDirectory() as temporary:
            source = pathlib.Path(temporary) / "malformed.json"
            source.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                PERIPHX.load_driver_manifest(source)


if __name__ == "__main__":
    unittest.main()
