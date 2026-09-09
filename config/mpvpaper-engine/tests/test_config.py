import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.config import (  # noqa: E402
    CANONICAL_DEFAULTS,
    CURRENT_SCHEMA_VERSION,
    LEGACY_DEFAULT_CONFIG,
    bounded_number,
    effective_output_config,
    load_config,
    load_config_data,
    normalize_legacy_config,
    normalize_v2_config,
    save_config,
    serialize_v2,
    to_legacy_dict,
    validate_output_name,
)
from mpvpaper_engine.models import ColorProfile, OutputMode  # noqa: E402
from mpvpaper_engine.paths import EnginePaths  # noqa: E402


def temporary_paths(root):
    root = Path(root)
    return EnginePaths.from_environment({
        "HOME": str(root / "home"),
        "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_RUNTIME_DIR": str(root / "runtime"),
    })


class ConfigTests(unittest.TestCase):
    def test_legacy_minimal_uses_exact_legacy_defaults(self):
        config = normalize_legacy_config({})

        legacy = to_legacy_dict(config)
        self.assertEqual(
            {key: legacy[key] for key in LEGACY_DEFAULT_CONFIG},
            LEGACY_DEFAULT_CONFIG,
        )
        self.assertEqual(legacy["assignments"], {})

    def test_legacy_complete_preserves_supported_values(self):
        source = {
            "wallpaper": "/wallpapers/night.mp4", "output": "eDP-1",
            "volume": 42, "speed": 1.25, "loop": False,
            "hardware_decode": False, "auto_pause": False,
            "autostart": False, "fit_mode": "contain", "brightness": 3,
            "contrast": 4, "gamma": 5, "saturation": 6, "hue": 7,
            "temperature": 7200, "red_balance": 8,
            "green_balance": 9, "blue_balance": 10,
        }

        legacy = to_legacy_dict(normalize_legacy_config(source))

        for key, value in source.items():
            self.assertEqual(legacy[key], value, key)

    def test_legacy_assignments_become_independent_outputs(self):
        config = normalize_legacy_config({
            "assignments": {
                "eDP-1": {"wallpaper": "/a.mp4", "volume": 4},
                "HDMI-A-1": {"wallpaper": "/b.png", "volume": 9},
            }
        })

        self.assertEqual(config.mode, OutputMode.INDEPENDENT)
        self.assertEqual(set(config.outputs), {"eDP-1", "HDMI-A-1"})
        self.assertEqual(config.outputs["eDP-1"]["wallpaper"], "/a.mp4")
        self.assertEqual(config.outputs["HDMI-A-1"]["volume"], 9)

    def test_global_star_output_is_preserved(self):
        config = normalize_legacy_config({
            "output": "*", "wallpaper": "/global.webm",
        })

        self.assertEqual(config.selected_output, "*")
        self.assertEqual(config.mode, OutputMode.SAME)
        self.assertIn("*", config.outputs)

    def test_edp_output_is_valid(self):
        self.assertTrue(validate_output_name("eDP-1"))

    def test_hdmi_output_is_valid(self):
        self.assertTrue(validate_output_name("HDMI-A-1"))

    def test_volume_is_bounded(self):
        self.assertEqual(normalize_legacy_config({"volume": -4}).defaults["volume"], 0)
        self.assertEqual(normalize_legacy_config({"volume": 500}).defaults["volume"], 100)

    def test_speed_is_bounded_and_infinity_keeps_legacy_behavior(self):
        self.assertEqual(bounded_number(0, 1.0, 0.1, 5.0, float), 0.1)
        self.assertEqual(bounded_number(float("inf"), 1.0, 0.1, 5.0, float), 5.0)
        self.assertEqual(bounded_number(float("nan"), 1.0, 0.1, 5.0, float), 1.0)

    def test_temperature_is_bounded(self):
        self.assertEqual(normalize_legacy_config({"temperature": 40}).defaults["temperature"], 1000)
        self.assertEqual(normalize_legacy_config({"temperature": 90000}).defaults["temperature"], 40000)

    def test_rgb_values_are_bounded(self):
        config = normalize_legacy_config({
            "red_balance": -500, "green_balance": 500, "blue_balance": 25,
        })
        self.assertEqual(config.defaults["red_balance"], -100)
        self.assertEqual(config.defaults["green_balance"], 100)
        self.assertEqual(config.defaults["blue_balance"], 25)

    def test_invalid_boolean_falls_back_instead_of_coercing_string(self):
        config = normalize_legacy_config({
            "loop": "false", "hardware_decode": "false", "autostart": 0,
        })
        legacy = to_legacy_dict(config)
        self.assertIs(legacy["loop"], True)
        self.assertIs(legacy["hardware_decode"], True)
        self.assertIs(legacy["autostart"], True)

    def test_invalid_output_is_rejected_and_falls_back_for_legacy(self):
        self.assertFalse(validate_output_name("../../DP-1"))
        self.assertFalse(validate_output_name(""))
        config = normalize_legacy_config({"output": "../../DP-1"})
        self.assertEqual(config.selected_output, "*")

    def test_absent_json_returns_safe_config_without_creating_any_path(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = temporary_paths(directory)
            config = load_config(paths)
            self.assertFalse(paths.config_home.exists())

        self.assertEqual(config.defaults["volume"], 0)
        self.assertIsNone(config.load_error)

    def test_invalid_json_is_logged_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = temporary_paths(directory)
            paths.config_home.mkdir(parents=True)
            damaged = "{invalid json\n"
            paths.config_file.write_text(damaged, encoding="utf-8")

            with self.assertLogs("mpvpaper_engine.config", level="WARNING"):
                config = load_config(paths)

            self.assertIsNotNone(config.load_error)
            self.assertEqual(paths.config_file.read_text(encoding="utf-8"), damaged)

    def test_v2_minimal_is_recognized(self):
        config = load_config_data({"schema_version": 2})

        self.assertEqual(config.schema_version, CURRENT_SCHEMA_VERSION)
        self.assertEqual(config.source_schema_version, CURRENT_SCHEMA_VERSION)
        self.assertEqual(config.defaults, CANONICAL_DEFAULTS)

    def test_v2_outputs_inherit_defaults(self):
        config = normalize_v2_config({
            "schema_version": 2,
            "defaults": {"volume": 17, "speed": 1.5},
            "outputs": {"DP-2": {"speed": 2.0}},
        })

        self.assertEqual(config.outputs["DP-2"]["volume"], 17)
        self.assertEqual(config.outputs["DP-2"]["speed"], 2.0)

    def test_effective_output_order_is_builtin_defaults_then_config_then_output(self):
        config = normalize_v2_config({
            "schema_version": 2,
            "defaults": {"volume": 12, "speed": 1.5},
            "outputs": {"DP-1": {"volume": 33}},
        })

        effective = effective_output_config(config, "DP-1")
        self.assertEqual(effective["volume"], 33)
        self.assertEqual(effective["speed"], 1.5)
        self.assertEqual(effective["fit_mode"], "cover")
        self.assertEqual(effective["output"], "DP-1")

    def test_original_color_profile_is_always_available(self):
        profile = normalize_v2_config({"schema_version": 2}).color_profiles["Original"]

        self.assertIsInstance(profile, ColorProfile)
        self.assertEqual(profile.temperature, 6500)
        self.assertEqual(profile.brightness, 0)

    def test_v2_roundtrip_in_memory_preserves_normalized_structure(self):
        first = normalize_v2_config({
            "schema_version": 2, "mode": "sync", "selected_output": "DP-1",
            "defaults": {"volume": 8},
            "outputs": {"DP-1": {"wallpaper": "/sync.mp4", "speed": 1.2}},
            "automation": {"enabled": True}, "ui": {"view": "grid"},
        })
        second = load_config_data(serialize_v2(first))

        self.assertEqual(second.mode, first.mode)
        self.assertEqual(second.defaults, first.defaults)
        self.assertEqual(second.outputs, first.outputs)
        self.assertEqual(second.automation, first.automation)
        self.assertEqual(second.ui, first.ui)

    def test_loading_valid_json_does_not_write_or_change_mtime(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = temporary_paths(directory)
            paths.config_home.mkdir(parents=True)
            paths.config_file.write_text('{"volume": 14}\n', encoding="utf-8")
            before = (paths.config_file.read_bytes(), paths.config_file.stat().st_mtime_ns)

            load_config(paths)

            after = (paths.config_file.read_bytes(), paths.config_file.stat().st_mtime_ns)
            self.assertEqual(after, before)

    def test_core_atomic_write_creates_private_file_and_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = temporary_paths(directory)
            save_config(normalize_v2_config({"schema_version": 2}), paths)

            self.assertEqual(paths.config_home.stat().st_mode & 0o777, 0o700)
            self.assertEqual(paths.config_file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(paths.config_file.read_text())["schema_version"], 2)
            self.assertEqual(list(paths.config_home.glob(".config.json-*")), [])

    def test_unknown_v2_keys_are_preserved_for_future_rewrite(self):
        source = {
            "schema_version": 2, "future_section": {"feature": 3},
            "defaults": {"future_default": "keep"},
            "outputs": {"DP-1": {"future_output": [1, 2]}},
            "color_profiles": {"Cinema": {"contrast": 4, "future_color": 7}},
        }

        serialized = serialize_v2(normalize_v2_config(source))

        self.assertEqual(serialized["future_section"], {"feature": 3})
        self.assertEqual(serialized["defaults"]["future_default"], "keep")
        self.assertEqual(serialized["outputs"]["DP-1"]["future_output"], [1, 2])
        self.assertEqual(serialized["color_profiles"]["Cinema"]["future_color"], 7)

    def test_import_and_normalization_have_no_filesystem_side_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = temporary_paths(root)
            normalize_legacy_config({"wallpaper": "/not-created.mp4"})
            normalize_v2_config({"schema_version": 2})
            self.assertFalse(paths.config_home.exists())
            self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
