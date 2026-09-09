#!/usr/bin/env python3
"""Non-destructive, anonymized hardware detection for Deblestia Setup."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import urllib.request


def language():
    value = os.environ.get("DEBLESTIA_LANG") or os.environ.get("LC_ALL") or \
        os.environ.get("LC_MESSAGES") or os.environ.get("LANG", "fr")
    return "en" if value.lower().replace("-", "_").startswith("en") else "fr"


def command(*args, timeout=3):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                                check=False)
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def os_release(path=Path("/etc/os-release")):
    values = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                values[key] = value.strip().strip('"')
    except OSError:
        pass
    return values


def memory_bytes(path=Path("/proc/meminfo")):
    try:
        for line in path.read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0


def disk_bytes(path=Path.home()):
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return 0


def network_available(opener=urllib.request.urlopen):
    try:
        with opener("https://deb.debian.org", timeout=3) as response:
            return getattr(response, "status", 200) < 400
    except Exception:
        return False


def detect(check_network=False):
    release = os_release()
    virtualization = command("systemd-detect-virt") or "none"
    pci = command("lspci", "-nnk")
    gpu_lines = [line.strip() for line in pci.splitlines()
                 if any(marker in line.casefold() for marker in
                        ("vga compatible", "3d controller", "display controller"))]
    renderer = ""
    glx = command("glxinfo", "-B")
    for line in glx.splitlines():
        if "OpenGL renderer string:" in line:
            renderer = line.split(":", 1)[1].strip()
    session = os.environ.get("XDG_SESSION_TYPE", "unknown")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    dm = command("systemctl", "show", "display-manager", "--property=Id", "--value")
    if dm in {"", "display-manager", "display-manager.service"}:
        try:
            dm = Path("/etc/X11/default-display-manager").read_text().strip()
            dm = Path(dm).name if dm else ""
        except OSError:
            dm = ""
    if not dm:
        display_link = Path("/etc/systemd/system/display-manager.service")
        try:
            dm = display_link.resolve().name.removesuffix(".service")
        except OSError:
            dm = "unknown"
    return {
        "distribution": release.get("ID", "unknown"),
        "distribution_name": release.get("PRETTY_NAME", "unknown"),
        "version": release.get("VERSION_ID", "unknown"),
        "codename": release.get("VERSION_CODENAME", "unknown"),
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "virtualization": virtualization,
        "cpu": platform.processor() or command("sh", "-c", "sed -n 's/^model name[[:space:]]*: //p' /proc/cpuinfo | head -1") or "unknown",
        "threads": os.cpu_count() or 1,
        "ram_bytes": memory_bytes(),
        "gpu": gpu_lines or ["unknown"],
        "opengl_renderer": renderer or "unavailable",
        "dri": sorted(path.name for path in Path("/dev/dri").glob("*")) if Path("/dev/dri").is_dir() else [],
        "session": session,
        "wayland": bool(os.environ.get("WAYLAND_DISPLAY")) or session == "wayland",
        "x11": bool(os.environ.get("DISPLAY")) or session == "x11",
        "hyprland": shutil.which("Hyprland") is not None or shutil.which("hyprctl") is not None,
        "gnome": "gnome" in desktop.casefold() or Path("/usr/share/xsessions/gnome.desktop").exists()
                 or Path("/usr/share/wayland-sessions/gnome.desktop").exists(),
        "display_manager": dm,
        "disk_free_bytes": disk_bytes(),
        "battery": any(Path("/sys/class/power_supply").glob("BAT*")),
        "network": network_available() if check_network else None,
        "commands": {name: shutil.which(name) is not None for name in (
            "Hyprland", "waybar", "kitty", "rofi", "jq", "playerctl", "cava",
            "mpvpaper", "ffmpeg", "python3", "cargo", "qs",
        )},
    }


def human(data, lang=None):
    lang = lang or language()
    gib = 1024 ** 3
    yes, no, missing, undetected = (("yes", "no", "missing", "not detected")
                                    if lang == "en" else
                                    ("oui", "non", "absent", "non détecté"))
    rows = (
        ("Debian", data["distribution_name"]), ("Architecture", data["architecture"]),
        (("Kernel" if lang == "en" else "Noyau"), data["kernel"]),
        ("Machine", data["virtualization"]),
        ("CPU / threads", f'{data["cpu"]} / {data["threads"]}'),
        ("RAM", f'{data["ram_bytes"] / gib:.1f} GiB'),
        ("GPU", " | ".join(data["gpu"])), ("OpenGL", data["opengl_renderer"]),
        ("/dev/dri", ", ".join(data["dri"]) or missing),
        ("Session", data["session"]), ("Hyprland", yes if data["hyprland"] else no),
        (("GNOME preserved" if lang == "en" else "GNOME conservable"), yes if data["gnome"] else undetected),
        ("Display manager", data["display_manager"]),
        (("Free disk space" if lang == "en" else "Disque libre"), f'{data["disk_free_bytes"] / gib:.1f} GiB'),
    )
    return "\n".join(f"{label:20} {value}" for label, value in rows)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--network", action="store_true")
    parser.add_argument("--lang", choices=("en", "fr"))
    args = parser.parse_args(argv)
    data = detect(args.network)
    print(json.dumps(data, ensure_ascii=False, indent=2) if args.json else human(data, args.lang))


if __name__ == "__main__":
    main()
