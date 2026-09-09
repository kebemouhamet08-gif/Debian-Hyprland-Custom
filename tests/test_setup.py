from pathlib import Path
import importlib.util
import unittest
from unittest import mock


ROOT = Path(__file__).parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "core" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HARDWARE = load("hardware")
COMPATIBILITY = load("compatibility")


def machine(**changes):
    data = {
        "distribution": "debian", "architecture": "x86_64", "dri": ["card0", "renderD128"],
        "gpu": ["Test GPU"],
        "opengl_renderer": "AMD Radeon", "virtualization": "none", "hyprland": False,
        "ram_bytes": 8 * 1024 ** 3, "threads": 8,
    }
    data.update(changes)
    return data


class SetupTests(unittest.TestCase):
    def test_memory_parser(self):
        with self.subTest("valid"):
            with mock.patch.object(Path, "read_text", return_value="MemTotal:       4096 kB\n"):
                self.assertEqual(HARDWARE.memory_bytes(Path("fixture")), 4096 * 1024)

    def test_missing_dri_is_hard_blocker(self):
        result = COMPATIBILITY.evaluate(machine(dri=[], ram_bytes=32 * 1024 ** 3))
        self.assertEqual(result["compatibility"], "UNSUPPORTED")
        self.assertEqual(result["profile"], "LEGACY")

    def test_virtual_machine_prefers_lite(self):
        result = COMPATIBILITY.evaluate(machine(virtualization="oracle", ram_bytes=16 * 1024 ** 3))
        self.assertEqual(result["compatibility"], "LIMITED")
        self.assertEqual(result["profile"], "LITE")

    def test_physical_machine_profiles(self):
        self.assertEqual(COMPATIBILITY.evaluate(machine(ram_bytes=6 * 1024 ** 3, threads=4))["profile"], "BALANCED")
        self.assertEqual(COMPATIBILITY.evaluate(machine(ram_bytes=16 * 1024 ** 3, threads=8))["profile"], "FULL")

    def test_report_has_no_identity_fields(self):
        with mock.patch.object(HARDWARE, "command", return_value=""):
            report = HARDWARE.detect()
        forbidden = {"username", "hostname", "ip", "mac", "ssid", "serial", "uuid", "home"}
        self.assertFalse(forbidden & set(report))

    def test_display_manager_uses_debian_default_file(self):
        original = Path.read_text
        def read_text(path, *args, **kwargs):
            if str(path) == "/etc/X11/default-display-manager":
                return "/usr/sbin/gdm3\n"
            return original(path, *args, **kwargs)
        with mock.patch.object(HARDWARE, "command", return_value=""), \
                mock.patch.object(Path, "read_text", read_text):
            self.assertEqual(HARDWARE.detect()["display_manager"], "gdm3")


if __name__ == "__main__":
    unittest.main()
