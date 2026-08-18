#!/usr/bin/env python3

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import re


CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "mpvpaper-engine"
CONFIG_FILE = CONFIG_DIR / "config.json"
UNIT_PREFIX = "mpvpaper-engine-wallpaper"
LEGACY_UNIT = f"{UNIT_PREFIX}.service"
DEFAULT_CONFIG = {
    "wallpaper": "",
    "output": "*",
    "volume": 0,
    "speed": 1.0,
    "loop": True,
    "hardware_decode": True,
    "auto_pause": True,
    "autostart": True,
}


def load_config():
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    config = {**DEFAULT_CONFIG, **data}
    if "assignments" not in config:
        config["assignments"] = {}
        if config["wallpaper"]:
            config["assignments"][config["output"]] = {
                key: config[key] for key in DEFAULT_CONFIG if key != "output"
            }
    return config


def save_config(config):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    temporary.replace(CONFIG_FILE)


def run(command, check=False):
    if os.environ.get("MPVPAPER_ENGINE_DRY_RUN") == "1":
        print(json.dumps(command))
        return subprocess.CompletedProcess(command, 0)
    return subprocess.run(command, check=check)


def unit_for_output(output):
    suffix = "all" if output == "*" else re.sub(r"[^A-Za-z0-9_.-]", "-", output)
    return f"{UNIT_PREFIX}-{suffix}.service"


def stop(output=None):
    if output is not None:
        run(["systemctl", "--user", "stop", unit_for_output(output)])
        return
    run(["systemctl", "--user", "stop", f"{UNIT_PREFIX}-*.service"])
    run(["systemctl", "--user", "stop", LEGACY_UNIT])
    run(["pkill", "-x", "mpvpaper"])


def mpv_options(config):
    options = ["load-scripts=no", f"speed={config['speed']}"]
    if config["loop"]:
        options.append("loop-file=inf")
    if config["hardware_decode"]:
        options.append("hwdec=auto-safe")
    if int(config["volume"]) <= 0:
        options.append("no-audio")
    else:
        options.extend(["audio=yes", f"volume={int(config['volume'])}"])
    return " ".join(options)


def play(config):
    wallpaper = Path(config["wallpaper"]).expanduser()
    if not wallpaper.is_file():
        raise SystemExit(f"Fond vidéo introuvable : {wallpaper}")
    if not shutil.which("mpvpaper"):
        raise SystemExit("mpvpaper n'est pas installé")

    if config["output"] == "*":
        stop()
    else:
        stop(config["output"])
        stop("*")
        run(["systemctl", "--user", "stop", LEGACY_UNIT])
    run(["pkill", "-x", "swww-daemon"])
    command = ["mpvpaper"]
    if config["auto_pause"]:
        command.extend(["--auto-pause", "--auto-mode", "full"])
    command.extend(["--mpv-options", mpv_options(config), config["output"], str(wallpaper)])
    run([
        "systemd-run", "--user", "--quiet", "--collect",
        f"--unit={unit_for_output(config['output'])}",
        *command,
    ], check=True)


def main():
    parser = argparse.ArgumentParser(description="Contrôleur de MPVpaper Engine")
    parser.add_argument("action", choices=("play", "stop", "restore", "status"))
    args = parser.parse_args()
    config = load_config()

    if args.action == "play":
        play(config)
    elif args.action == "stop":
        stop()
    elif args.action == "restore":
        assignments = config.get("assignments", {})
        if "*" in assignments:
            profile = {**DEFAULT_CONFIG, **assignments["*"], "output": "*"}
            if profile["autostart"] and profile["wallpaper"]:
                play(profile)
        else:
            for output, assignment in assignments.items():
                profile = {**DEFAULT_CONFIG, **assignment, "output": output}
                if profile["autostart"] and profile["wallpaper"]:
                    play(profile)
    else:
        result = subprocess.run(
            ["systemctl", "--user", "list-units", f"{UNIT_PREFIX}-*.service",
             "--state=active", "--no-legend"],
            capture_output=True, text=True, check=False,
        )
        count = len([line for line in result.stdout.splitlines() if line.strip()])
        print(f"active:{count}" if count else "inactive")
        return 0 if count else 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
