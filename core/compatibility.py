#!/usr/bin/env python3
"""Compatibility and performance are deliberately evaluated separately."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from hardware import detect  # noqa: E402


def evaluate(data):
    reasons = []
    supported_arch = data["architecture"] in {"x86_64", "amd64", "aarch64", "arm64"}
    debian = data["distribution"] == "debian"
    gpu_known = bool(data["gpu"]) and data["gpu"] != ["unknown"]
    restricted_environment = data["virtualization"].startswith("container")
    graphics = bool(data["dri"]) or (restricted_environment and gpu_known and data["hyprland"])
    software = "llvmpipe" in data["opengl_renderer"].casefold()
    compatibility = "RECOMMENDED"
    if not debian or not supported_arch or not graphics:
        compatibility = "UNSUPPORTED"
    elif software or (data["virtualization"] != "none" and not restricted_environment):
        compatibility = "LIMITED"
    elif not data["hyprland"]:
        compatibility = "COMPATIBLE"
    if not debian:
        reasons.append("distribution non Debian")
    if not supported_arch:
        reasons.append("architecture non prise en charge")
    if not graphics:
        reasons.append("accélération graphique non détectée")
    elif restricted_environment and not data["dri"]:
        reasons.append("/dev/dri masqué par l’environnement de diagnostic ; session Hyprland utilisée comme preuve")
    if software:
        reasons.append("rendu logiciel llvmpipe")
    ram_gib = data["ram_bytes"] / 1024 ** 3
    threads = data["threads"]
    if compatibility == "UNSUPPORTED":
        profile = "LEGACY"
    elif (data["virtualization"] != "none" and not restricted_environment) or software or ram_gib < 4 or threads < 4:
        profile = "LITE"
    elif ram_gib >= 12 and threads >= 8:
        profile = "FULL"
    else:
        profile = "BALANCED"
    return {
        "compatibility": compatibility,
        "profile": profile,
        "performance_score": max(0, min(100, round(ram_gib * 3 + threads * 4))),
        "reasons": reasons,
        "features": {
            "hyprland": compatibility,
            "deblestia": "UNSUPPORTED" if compatibility == "UNSUPPORTED" else "RECOMMENDED",
            "video_wallpaper": "LIMITED" if profile in {"LEGACY", "LITE"} else "COMPATIBLE",
            "blur": "LIMITED" if profile in {"LEGACY", "LITE"} else "COMPATIBLE",
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--lang", choices=("en", "fr"))
    args = parser.parse_args(argv)
    result = evaluate(detect())
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        locale = args.lang or os.environ.get("DEBLESTIA_LANG") or os.environ.get("LANG", "fr")
        english = locale.lower().replace("-", "_").startswith("en")
        print(f'{"Compatibility" if english else "Compatibilité":20} {result["compatibility"]}')
        print(f'{"Recommended profile" if english else "Profil recommandé":20} {result["profile"]}')
        print(f'Performance         {result["performance_score"]}/100')
        for reason in result["reasons"]:
            translations = {
                "distribution non Debian": "non-Debian distribution",
                "architecture non prise en charge": "unsupported architecture",
                "accélération graphique non détectée": "graphics acceleration not detected",
                "/dev/dri masqué par l’environnement de diagnostic ; session Hyprland utilisée comme preuve":
                    "/dev/dri hidden by the diagnostic environment; Hyprland session used as evidence",
                "rendu logiciel llvmpipe": "llvmpipe software rendering",
            }
            label = "WARNING" if english else "ATTENTION"
            message = translations.get(reason, reason) if english else reason
            print(f'{label:20} {message}')


if __name__ == "__main__":
    main()
