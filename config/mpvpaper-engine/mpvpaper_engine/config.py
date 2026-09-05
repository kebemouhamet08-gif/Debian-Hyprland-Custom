"""Versioned configuration and legacy compatibility for MPVpaper Engine."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import json
import logging
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from .models import ColorProfile, OutputMode
from .paths import EnginePaths


CURRENT_SCHEMA_VERSION = 2
LOGGER = logging.getLogger(__name__)
COLOR_KEYS = (
    "brightness", "contrast", "gamma", "saturation", "hue", "temperature",
    "red_balance", "green_balance", "blue_balance",
)
COLOR_DEFAULTS = {
    "brightness": 0, "contrast": 0, "gamma": 0, "saturation": 0, "hue": 0,
    "temperature": 6500, "red_balance": 0, "green_balance": 0, "blue_balance": 0,
}
LEGACY_DEFAULT_CONFIG = {
    "wallpaper": "", "output": "*", "volume": 0, "speed": 1.0,
    "loop": True, "hardware_decode": True, "auto_pause": True,
    "autostart": True, "fit_mode": "cover", **COLOR_DEFAULTS,
}
CANONICAL_DEFAULTS = {
    "wallpaper": "", "volume": 0, "muted": True, "speed": 1.0,
    "loop": True, "fit_mode": "cover", "hardware_decode": "auto",
    "auto_pause": True, "autostart": True, "performance_profile": "auto",
    "color_profile": "Original", "theme_sync": "off", **COLOR_DEFAULTS,
}
HUD_DEFAULTS = {"enabled": True, "position": {"x": 0.18, "y": 0.30}, "scale": 1.0,
                "opacity": 1.0, "username": "ムハメト・ケベ", "elements": {}}
LEGACY_KEYS = frozenset((*LEGACY_DEFAULT_CONFIG, "assignments"))


@dataclass(slots=True)
class EngineConfig:
    schema_version: int = CURRENT_SCHEMA_VERSION
    mode: OutputMode = OutputMode.INDEPENDENT
    defaults: dict[str, Any] = field(default_factory=lambda: dict(CANONICAL_DEFAULTS))
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    color_profiles: dict[str, ColorProfile] = field(
        default_factory=lambda: {"Original": ColorProfile()}
    )
    automation: dict[str, Any] = field(default_factory=dict)
    cache: dict[str, Any] = field(default_factory=dict)
    theme_sync: dict[str, Any] = field(default_factory=dict)
    ui: dict[str, Any] = field(default_factory=dict)
    selected_output: str = "*"
    selected_profile: dict[str, Any] = field(default_factory=lambda: dict(CANONICAL_DEFAULTS))
    source_schema_version: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)
    load_error: str | None = None


def bounded_number(value, default, minimum, maximum, number_type=int):
    try:
        parsed = number_type(value)
        if isinstance(parsed, float) and math.isnan(parsed):
            return default
    except (TypeError, ValueError, OverflowError):
        return default
    return max(minimum, min(maximum, parsed))


def validate_output_name(value):
    return isinstance(value, str) and bool(re.fullmatch(
        r"(?:\*|[A-Za-z0-9][A-Za-z0-9_.-]{0,127})", value
    ))


def _bool(source, key, default):
    return source[key] if isinstance(source.get(key), bool) else default


def _canonical_profile(source, base=None):
    source = source if isinstance(source, dict) else {}
    profile = {**CANONICAL_DEFAULTS, **(base or {})}
    wallpaper = source.get("wallpaper", profile["wallpaper"])
    profile["wallpaper"] = wallpaper if isinstance(wallpaper, str) else profile["wallpaper"]
    profile["volume"] = bounded_number(source.get("volume"), profile["volume"], 0, 100)
    profile["speed"] = bounded_number(source.get("speed"), profile["speed"], 0.1, 5.0, float)
    for key in ("muted", "loop", "auto_pause", "autostart"):
        profile[key] = _bool(source, key, profile[key])
    hardware = source.get("hardware_decode", profile["hardware_decode"])
    if isinstance(hardware, bool):
        hardware = "auto" if hardware else "disabled"
    profile["hardware_decode"] = (
        hardware if hardware in {"auto", "enabled", "disabled"}
        else profile["hardware_decode"]
    )
    if source.get("fit_mode") in {"cover", "contain", "stretch"}:
        profile["fit_mode"] = source["fit_mode"]
    if source.get("performance_profile") in {"auto", "eco", "balanced", "quality"}:
        profile["performance_profile"] = source["performance_profile"]
    if isinstance(source.get("color_profile"), str) and source["color_profile"]:
        profile["color_profile"] = source["color_profile"]
    if source.get("theme_sync") in {"off", "on_apply", "always"}:
        profile["theme_sync"] = source["theme_sync"]
    for key in COLOR_KEYS:
        low, high = ((1000, 40000) if key == "temperature" else (-100, 100))
        profile[key] = bounded_number(source.get(key), profile[key], low, high)
    return profile


def normalize_legacy_profile(data, output="*"):
    canonical = _canonical_profile(data)
    result = _canonical_to_legacy(canonical)
    requested = data.get("output", output) if isinstance(data, dict) else output
    result["output"] = requested if validate_output_name(requested) else output
    return result


def _legacy_to_canonical(data):
    return _canonical_profile(data)


def _canonical_to_legacy(profile):
    return {
        "wallpaper": profile.get("wallpaper", ""),
        "volume": bounded_number(profile.get("volume"), 0, 0, 100),
        "speed": bounded_number(profile.get("speed"), 1.0, 0.1, 5.0, float),
        "loop": _bool(profile, "loop", True),
        "hardware_decode": profile.get("hardware_decode") != "disabled",
        "auto_pause": _bool(profile, "auto_pause", True),
        "autostart": _bool(profile, "autostart", True),
        "fit_mode": profile.get("fit_mode", "cover"),
        **{key: bounded_number(
            profile.get(key), COLOR_DEFAULTS[key],
            1000 if key == "temperature" else -100,
            40000 if key == "temperature" else 100,
        ) for key in COLOR_KEYS},
    }


def _color_profile(name, data):
    values = _canonical_profile(data)
    return ColorProfile(name=name, **{key: values[key] for key in COLOR_KEYS})


def normalize_legacy_config(data):
    raw = deepcopy(data) if isinstance(data, dict) else {}
    top = normalize_legacy_profile(raw)
    selected = _legacy_to_canonical(top)
    selected_output = top["output"]
    outputs = {}
    assignments = raw.get("assignments")
    if isinstance(assignments, dict):
        for output, assignment in assignments.items():
            if validate_output_name(output) and isinstance(assignment, dict):
                outputs[output] = _legacy_to_canonical(
                    normalize_legacy_profile(assignment, output)
                )
    elif top["wallpaper"]:
        outputs[selected_output] = dict(selected)
    mode = OutputMode.SAME if set(outputs) == {"*"} else OutputMode.INDEPENDENT
    return EngineConfig(
        mode=mode, defaults=dict(selected), outputs=outputs,
        selected_output=selected_output, selected_profile=selected,
        source_schema_version=None, raw_data=raw,
        ui={"hud": deepcopy(HUD_DEFAULTS)},
    )


def normalize_v2_config(data):
    raw = deepcopy(data) if isinstance(data, dict) else {}
    defaults = _canonical_profile(raw.get("defaults"))
    outputs = {}
    for output, override in (raw.get("outputs") or {}).items() if isinstance(raw.get("outputs"), dict) else ():
        if validate_output_name(output) and isinstance(override, dict):
            outputs[output] = _canonical_profile(override, defaults)
    try:
        mode = OutputMode(raw.get("mode", OutputMode.INDEPENDENT.value))
    except ValueError:
        mode = OutputMode.INDEPENDENT
    selected_output = raw.get("selected_output", "*")
    if not validate_output_name(selected_output):
        selected_output = "*"
    colors = {"Original": ColorProfile()}
    if isinstance(raw.get("color_profiles"), dict):
        for name, values in raw["color_profiles"].items():
            if isinstance(name, str) and name and isinstance(values, dict):
                colors[name] = _color_profile(name, values)
    selected = _canonical_profile(outputs.get(selected_output), defaults)
    sections = {
        key: deepcopy(raw.get(key)) if isinstance(raw.get(key), dict) else {}
        for key in ("automation", "cache", "theme_sync", "ui")
    }
    sections["ui"].setdefault("hud", deepcopy(HUD_DEFAULTS))
    return EngineConfig(
        mode=mode, defaults=defaults, outputs=outputs, color_profiles=colors,
        selected_output=selected_output, selected_profile=selected,
        source_schema_version=CURRENT_SCHEMA_VERSION, raw_data=raw, **sections,
    )


def load_config_data(data):
    if isinstance(data, dict) and data.get("schema_version") == CURRENT_SCHEMA_VERSION:
        return normalize_v2_config(data)
    return normalize_legacy_config(data)


def load_config(paths=None):
    engine_paths = paths or EnginePaths.from_environment()
    try:
        data = json.loads(engine_paths.config_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return normalize_legacy_config({})
    except (OSError, json.JSONDecodeError) as error:
        LOGGER.warning("Unable to read configuration %s: %s", engine_paths.config_file, error)
        config = normalize_legacy_config({})
        config.load_error = str(error)
        return config
    return load_config_data(data)


def effective_output_config(config, output):
    if not validate_output_name(output):
        raise ValueError("invalid output name")
    return {**CANONICAL_DEFAULTS, **config.defaults, **config.outputs.get(output, {}),
            "output": output}


def to_legacy_dict(config):
    result = _canonical_to_legacy(config.selected_profile)
    result["output"] = config.selected_output
    result["assignments"] = {
        output: _canonical_to_legacy(profile) for output, profile in config.outputs.items()
    }
    return result


def load_legacy_compatible_config(config_file):
    paths = EnginePaths.from_environment()
    paths = EnginePaths(**{**asdict(paths), "config_file": Path(config_file)})
    return to_legacy_dict(load_config(paths))


def serialize_v2(config):
    result = deepcopy(config.raw_data) if config.source_schema_version == CURRENT_SCHEMA_VERSION else {}
    raw_defaults = result.get("defaults") if isinstance(result.get("defaults"), dict) else {}
    serialized_defaults = {**deepcopy(raw_defaults), **deepcopy(config.defaults)}
    raw_outputs = result.get("outputs") if isinstance(result.get("outputs"), dict) else {}
    serialized_outputs = {}
    for output, profile in config.outputs.items():
        raw_profile = raw_outputs.get(output)
        preserved = deepcopy(raw_profile) if isinstance(raw_profile, dict) else {}
        serialized_outputs[output] = {**preserved, **deepcopy(profile)}
    raw_colors = (
        result.get("color_profiles")
        if isinstance(result.get("color_profiles"), dict) else {}
    )
    serialized_colors = {}
    for name, profile in config.color_profiles.items():
        raw_profile = raw_colors.get(name)
        preserved = deepcopy(raw_profile) if isinstance(raw_profile, dict) else {}
        serialized_colors[name] = {**preserved, **asdict(profile)}
    result.update({
        "schema_version": CURRENT_SCHEMA_VERSION,
        "mode": config.mode.value,
        "selected_output": config.selected_output,
        "defaults": serialized_defaults,
        "outputs": serialized_outputs,
        "color_profiles": serialized_colors,
        "automation": deepcopy(config.automation), "cache": deepcopy(config.cache),
        "theme_sync": deepcopy(config.theme_sync), "ui": deepcopy(config.ui),
    })
    if config.source_schema_version is None:
        unknown = {key: deepcopy(value) for key, value in config.raw_data.items()
                   if key not in LEGACY_KEYS}
        if unknown:
            result["legacy_unknown"] = unknown
    return result


def _atomic_write(data, destination):
    destination = Path(destination)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=f".{destination.name}-", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def save_config(config, paths=None):
    engine_paths = paths or EnginePaths.from_environment()
    _atomic_write(serialize_v2(config), engine_paths.config_file)


def save_legacy_config(config, config_file):
    _atomic_write(config, config_file)


def migrate_config(paths=None) -> dict[str, Any]:
    """Transactionally migrate a legacy config, preserving its exact original bytes."""
    engine_paths = paths or EnginePaths.from_environment()
    source = engine_paths.config_file
    staging = source.with_name(source.name + ".v2.new")
    backup = source.with_name(source.name + ".v1.backup")
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"migrated": False, "reason": "config missing"}
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"legacy config is unreadable: {error}") from error
    if isinstance(raw, dict) and raw.get("schema_version") == CURRENT_SCHEMA_VERSION:
        return {"migrated": False, "reason": "already v2"}
    normalized = normalize_legacy_config(raw)
    _atomic_write(serialize_v2(normalized), staging)
    try:
        check = json.loads(staging.read_text(encoding="utf-8"))
        restored = normalize_v2_config(check)
        if restored.source_schema_version != CURRENT_SCHEMA_VERSION:
            raise ValueError("staged config failed schema validation")
        if to_legacy_dict(restored) != to_legacy_dict(normalized):
            raise ValueError("staged config failed legacy round-trip validation")
        if not backup.exists():
            shutil.copy2(source, backup)
            backup.chmod(0o600)
        os.replace(staging, source)
        source.chmod(0o600)
    finally:
        try:
            staging.unlink()
        except FileNotFoundError:
            pass
    return {"migrated": True, "backup": str(backup), "schema_version": CURRENT_SCHEMA_VERSION}
