from pathlib import Path
import json
import sys
import tempfile
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.config import (  # noqa: E402
    normalize_legacy_config,
    migrate_config,
    serialize_v2,
    to_legacy_dict,
)
from mpvpaper_engine.models import OutputMode  # noqa: E402
from mpvpaper_engine.paths import EnginePaths  # noqa: E402


GOLDEN_LEGACY = {
    "wallpaper": "/wallpapers/laptop.mp4",
    "output": "eDP-1",
    "volume": 11,
    "speed": 1.15,
    "loop": False,
    "hardware_decode": False,
    "auto_pause": False,
    "autostart": True,
    "brightness": 1,
    "contrast": 2,
    "gamma": 3,
    "saturation": 4,
    "hue": 5,
    "temperature": 6800,
    "red_balance": 6,
    "green_balance": 7,
    "blue_balance": 8,
    "assignments": {
        "eDP-1": {
            "wallpaper": "/wallpapers/laptop.mp4", "volume": 11,
            "speed": 1.15, "loop": False, "hardware_decode": False,
            "auto_pause": False, "autostart": True, "brightness": 1,
            "contrast": 2, "gamma": 3, "saturation": 4, "hue": 5,
            "temperature": 6800, "red_balance": 6,
            "green_balance": 7, "blue_balance": 8,
        },
        "HDMI-A-1": {
            "wallpaper": "/wallpapers/external.png", "volume": 37,
            "speed": 0.75, "loop": True, "hardware_decode": True,
            "auto_pause": True, "autostart": False, "brightness": -9,
            "contrast": 12, "gamma": -3, "saturation": 18, "hue": -4,
            "temperature": 5100, "red_balance": -8,
            "green_balance": 2, "blue_balance": 14,
        },
    },
}


class LegacyMigrationTests(unittest.TestCase):
    def test_golden_two_monitor_legacy_data_is_lossless_in_memory(self):
        config = normalize_legacy_config(GOLDEN_LEGACY)
        restored = to_legacy_dict(config)

        self.assertEqual(config.mode, OutputMode.INDEPENDENT)
        self.assertEqual(config.selected_output, "eDP-1")
        self.assertEqual(set(config.outputs), {"eDP-1", "HDMI-A-1"})
        for key, value in GOLDEN_LEGACY.items():
            if key != "assignments":
                self.assertEqual(restored[key], value, key)
        for output, expected in GOLDEN_LEGACY["assignments"].items():
            for key, value in expected.items():
                self.assertEqual(restored["assignments"][output][key], value, f"{output}.{key}")

    def test_legacy_to_v2_serialization_is_explicit_only(self):
        config = normalize_legacy_config(GOLDEN_LEGACY)

        serialized = serialize_v2(config)

        self.assertEqual(serialized["schema_version"], 2)
        self.assertEqual(serialized["outputs"]["eDP-1"]["wallpaper"], "/wallpapers/laptop.mp4")
        self.assertEqual(serialized["outputs"]["HDMI-A-1"]["wallpaper"], "/wallpapers/external.png")
        self.assertEqual(serialized["outputs"]["HDMI-A-1"]["autostart"], False)

    def test_transactional_migration_preserves_exact_backup_and_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = EnginePaths.from_environment({
                "HOME": str(root), "XDG_CONFIG_HOME": str(root / "config"),
                "XDG_DATA_HOME": str(root / "data"), "XDG_CACHE_HOME": str(root / "cache"),
                "XDG_RUNTIME_DIR": str(root / "runtime"),
            })
            paths.config_home.mkdir(parents=True)
            original = json.dumps(GOLDEN_LEGACY, indent=3) + "\n"
            paths.config_file.write_text(original, encoding="utf-8")
            result = migrate_config(paths)
            self.assertTrue(result["migrated"])
            self.assertEqual(
                paths.config_file.with_name("config.json.v1.backup").read_text(), original
            )
            migrated = json.loads(paths.config_file.read_text())
            self.assertEqual(migrated["schema_version"], 2)
            self.assertFalse(paths.config_file.with_name("config.json.v2.new").exists())

    def test_v2_config_is_never_rewritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = EnginePaths.from_environment({"HOME": str(root)})
            paths.config_home.mkdir(parents=True)
            text = '{"schema_version":2,"custom":"kept"}\n'
            paths.config_file.write_text(text)
            self.assertFalse(migrate_config(paths)["migrated"])
            self.assertEqual(paths.config_file.read_text(), text)


if __name__ == "__main__":
    unittest.main()
