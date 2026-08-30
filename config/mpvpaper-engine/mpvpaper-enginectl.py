#!/usr/bin/env python3

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import re
import secrets
import socket
import tempfile


CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "mpvpaper-engine"
CONFIG_FILE = CONFIG_DIR / "config.json"
UNIT_PREFIX = "mpvpaper-engine-wallpaper"
LEGACY_UNIT = f"{UNIT_PREFIX}.service"
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/mpvpaper-engine-{os.getuid()}")) / "mpvpaper-engine"
COLOR_DEFAULTS = {
    "brightness": 0,
    "contrast": 0,
    "gamma": 0,
    "saturation": 0,
    "hue": 0,
    "temperature": 6500,
    "red_balance": 0,
    "green_balance": 0,
    "blue_balance": 0,
}
DEFAULT_CONFIG = {
    "wallpaper": "",
    "output": "*",
    "volume": 0,
    "speed": 1.0,
    "loop": True,
    "hardware_decode": True,
    "auto_pause": True,
    "autostart": True,
    **COLOR_DEFAULTS,
}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"}
WALLPAPER_DIRS = (
    Path.home() / "Pictures" / "Wallpapers" / "Live",
    Path.home() / "Pictures" / "wallpapers",
)


def bounded_number(value, default, minimum, maximum, number_type=int):
    try:
        parsed = number_type(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(minimum, min(maximum, parsed))


def valid_output_name(value):
    return isinstance(value, str) and bool(re.fullmatch(
        r"(?:\*|[A-Za-z0-9][A-Za-z0-9_.-]{0,127})", value
    ))


def normalize_profile(data, output="*"):
    source = data if isinstance(data, dict) else {}
    profile = dict(DEFAULT_CONFIG)
    wallpaper = source.get("wallpaper", "")
    profile["wallpaper"] = wallpaper if isinstance(wallpaper, str) else ""
    requested_output = source.get("output", output)
    profile["output"] = requested_output if valid_output_name(requested_output) else output
    profile["volume"] = bounded_number(source.get("volume"), 0, 0, 100)
    profile["speed"] = bounded_number(source.get("speed"), 1.0, 0.1, 5.0, float)
    for key in ("loop", "hardware_decode", "auto_pause", "autostart"):
        if isinstance(source.get(key), bool):
            profile[key] = source[key]
    for key in ("brightness", "contrast", "gamma", "saturation", "hue",
                "red_balance", "green_balance", "blue_balance"):
        profile[key] = bounded_number(source.get(key), COLOR_DEFAULTS[key], -100, 100)
    profile["temperature"] = bounded_number(source.get("temperature"), 6500, 1000, 40000)
    return profile


def load_config():
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    config = normalize_profile(data)
    assignments = data.get("assignments") if isinstance(data, dict) else None
    config["assignments"] = {}
    if isinstance(assignments, dict):
        for output, assignment in assignments.items():
            if not valid_output_name(output) or not isinstance(assignment, dict):
                continue
            profile = normalize_profile(assignment, output=output)
            config["assignments"][output] = {
                key: profile[key] for key in DEFAULT_CONFIG if key != "output"
            }
    elif config["wallpaper"]:
        config["assignments"] = {}
        config["assignments"][config["output"]] = {
            key: config[key] for key in DEFAULT_CONFIG if key != "output"
        }
    return config


def save_config(config):
    CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    CONFIG_DIR.chmod(0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=CONFIG_DIR, prefix=".config-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(config, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, CONFIG_FILE)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def run(command, check=False):
    if os.environ.get("MPVPAPER_ENGINE_DRY_RUN") == "1":
        print(json.dumps(command))
        return subprocess.CompletedProcess(command, 0)
    return subprocess.run(command, check=check)


def stop_static_wallpaper_services():
    """Empêche les anciens changeurs d'images de recouvrir le fond vidéo."""
    run(["pkill", "-f", r"(^|/)WallpaperAutoChange\.sh(?: |$)"])
    run(["pkill", "-x", "swww-daemon"])


def unit_for_output(output):
    suffix = "all" if output == "*" else re.sub(r"[^A-Za-z0-9_.-]", "-", output)
    return f"{UNIT_PREFIX}-{suffix}.service"


def socket_for_output(output):
    suffix = "all" if output == "*" else re.sub(r"[^A-Za-z0-9_.-]", "-", output)
    return RUNTIME_DIR / f"{suffix}.sock"


def color_filter(config):
    temperature = max(1000, min(40000, int(config.get("temperature", 6500))))
    red = max(-100, min(100, int(config.get("red_balance", 0)))) / 100
    green = max(-100, min(100, int(config.get("green_balance", 0)))) / 100
    blue = max(-100, min(100, int(config.get("blue_balance", 0)))) / 100
    return (
        f"lavfi=[colortemperature=temperature={temperature},"
        f"colorbalance=rm={red:.2f}:gm={green:.2f}:bm={blue:.2f}]"
    )


def ipc_request(output, command):
    path = socket_for_output(output)
    if not path.exists():
        raise RuntimeError(f"aucun fond MPVpaper actif sur {output}")
    payload = json.dumps({"command": command}).encode() + b"\n"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        client.connect(str(path))
        client.sendall(payload)
        response = client.makefile("rb").readline()
    result = json.loads(response)
    if result.get("error") != "success":
        raise RuntimeError(result.get("error", "erreur IPC mpv"))
    return result


def apply_colors(config):
    output = config.get("output", "*")
    for name in ("brightness", "contrast", "gamma", "saturation", "hue"):
        value = max(-100, min(100, int(config.get(name, 0))))
        ipc_request(output, ["set_property", name, value])
    ipc_request(output, ["set_property", "vf", color_filter(config)])


def capture_path(output):
    suffix = "all" if output == "*" else re.sub(r"[^A-Za-z0-9_.-]", "-", output)
    directory = RUNTIME_DIR / "captures"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    return directory / f"{suffix}.png"


def capture_filter(config):
    brightness = max(-100, min(100, int(config.get("brightness", 0)))) / 100
    contrast = 1 + max(-100, min(100, int(config.get("contrast", 0)))) / 100
    gamma = 2 ** (max(-100, min(100, int(config.get("gamma", 0)))) / 100)
    saturation = 1 + max(-100, min(100, int(config.get("saturation", 0)))) / 100
    hue = max(-100, min(100, int(config.get("hue", 0)))) * 1.8
    return (
        f"eq=brightness={brightness:.2f}:contrast={contrast:.2f}:gamma={gamma:.3f}:"
        f"saturation={saturation:.2f},hue=h={hue:.1f},"
        + color_filter(config).removeprefix("lavfi=[").removesuffix("]")
    )


def capture_wallpaper(output, config):
    source_result = ipc_request(output, ["get_property", "path"])
    position_result = ipc_request(output, ["get_property", "time-pos"])
    source = Path(str(source_result.get("data", ""))).expanduser()
    if not source.is_file():
        raise RuntimeError("le fichier du fond MPV actif est introuvable")
    position = max(0, float(position_result.get("data") or 0))
    return capture_source_wallpaper(source, output, config, position)


def capture_source_wallpaper(source, output, config, position=2.0):
    source = Path(source).expanduser()
    if not source.is_file() or source.suffix.lower() not in VIDEO_EXTENSIONS:
        raise RuntimeError("le fond vidéo choisi est introuvable ou non pris en charge")
    destination = capture_path(output)
    temporary = destination.with_name(f".{destination.stem}.new.png")
    result = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{position:.3f}", "-i", str(source), "-frames:v", "1",
        "-vf", capture_filter(config), str(temporary),
    ], capture_output=True, text=True, timeout=10, check=False)
    if result.returncode != 0 or not temporary.is_file() or not temporary.stat().st_size:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(result.stderr.strip() or "extraction de la frame impossible")
    temporary.replace(destination)
    destination.chmod(0o600)
    return destination


def adapt_desktop_theme(output, config, wallpaper=None):
    """Génère les palettes du bureau depuis une frame, sans remplacer le fond vidéo."""
    frame = (capture_source_wallpaper(wallpaper, output, config)
             if wallpaper else capture_wallpaper(output, config))
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    integrations = []
    failures = []

    nova_candidates = (
        config_home / "quickshell" / "deblestia-nova" / "scripts" / "colors" / "switchwall.sh",
        config_home / "quickshell" / "ii" / "scripts" / "colors" / "switchwall.sh",
    )
    nova_script = next((path for path in nova_candidates if path.is_file()), None)
    if nova_script:
        result = subprocess.run(
            [str(nova_script), "--noswitch", "--image", str(frame)],
            capture_output=True, text=True, timeout=180, check=False,
        )
        if result.returncode == 0:
            integrations.append("Nova et applications")
        else:
            failures.append(result.stderr.strip() or result.stdout.strip() or "palette Nova")

    waybar_script = config_home / "hypr" / "UserScripts" / "WaybarWallpaperSync.sh"
    if waybar_script.is_file():
        result = subprocess.run(
            [str(waybar_script), "--wallpaper", str(frame), "--reload", "--no-start"],
            capture_output=True, text=True, timeout=60, check=False,
        )
        if result.returncode == 0:
            integrations.append("Waybar")
        else:
            failures.append(result.stderr.strip() or "palette Waybar")

    if not nova_script and not waybar_script.is_file():
        wallust = shutil.which("wallust")
        if wallust:
            result = subprocess.run(
                [wallust, "run", "-s", str(frame)], capture_output=True,
                text=True, timeout=60, check=False,
            )
            if result.returncode == 0:
                integrations.append("Wallust")
            else:
                failures.append(result.stderr.strip() or "palette Wallust")

    if failures:
        raise RuntimeError("; ".join(failures))
    if not integrations:
        raise RuntimeError("aucun moteur de thème compatible n’est installé")
    return frame, integrations


def stop(output=None):
    if output is not None:
        run(["systemctl", "--user", "stop", unit_for_output(output)])
        return
    run(["systemctl", "--user", "stop", f"{UNIT_PREFIX}-*.service"])
    run(["systemctl", "--user", "stop", LEGACY_UNIT])
    run(["pkill", "-x", "mpvpaper"])


def mpv_options(config):
    RUNTIME_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    RUNTIME_DIR.chmod(0o700)
    ipc_socket = socket_for_output(config["output"])
    if ipc_socket.exists() and not ipc_socket.is_socket():
        raise RuntimeError(f"le chemin IPC existe mais n'est pas un socket : {ipc_socket}")
    try:
        ipc_socket.unlink()
    except FileNotFoundError:
        pass
    options = [
        "load-scripts=no",
        f"speed={config['speed']}",
        f"input-ipc-server={ipc_socket}",
        *(f"{name}={int(config.get(name, 0))}" for name in (
            "brightness", "contrast", "gamma", "saturation", "hue"
        )),
        f"vf={color_filter(config)}",
    ]
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
    stop_static_wallpaper_services()
    command = ["mpvpaper"]
    if config["auto_pause"]:
        command.extend(["--auto-pause", "--auto-mode", "full"])
    command.extend(["--mpv-options", mpv_options(config), config["output"], str(wallpaper)])
    run([
        "systemd-run", "--user", "--quiet", "--collect",
        f"--unit={unit_for_output(config['output'])}",
        *command,
    ], check=True)


def random_wallpapers():
    wallpapers = []
    seen = set()
    for directory in WALLPAPER_DIRS:
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
                resolved = path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    wallpapers.append(path)
    return wallpapers


def play_random(config):
    wallpapers = random_wallpapers()
    if not wallpapers:
        locations = ", ".join(str(path) for path in WALLPAPER_DIRS)
        raise SystemExit(f"Aucun fond vidéo trouvé dans : {locations}")

    current = Path(config.get("wallpaper", "")).expanduser()
    alternatives = [path for path in wallpapers if path != current]
    selected = secrets.choice(alternatives or wallpapers)
    config["wallpaper"] = str(selected)

    assignments = config.setdefault("assignments", {})
    output = config.get("output", "*")
    if output == "*":
        assignments.clear()
    else:
        assignments.pop("*", None)
    assignments[output] = {
        key: config[key] for key in DEFAULT_CONFIG if key != "output"
    }
    save_config(config)
    play(config)
    print(selected)


def main():
    parser = argparse.ArgumentParser(description="Contrôleur de MPVpaper Engine")
    parser.add_argument("action", choices=(
        "play", "random", "stop", "restore", "status", "apply-colors", "preview-colors",
        "capture", "adapt-theme",
    ))
    parser.add_argument("--output", default=None, help="écran ciblé pour les couleurs")
    parser.add_argument("--settings", default=None, help="réglages couleur JSON à prévisualiser")
    parser.add_argument("--wallpaper", default=None, help="fond vidéo choisi pour la palette")
    args = parser.parse_args()
    config = load_config()

    if args.action == "play":
        play(config)
    elif args.action == "random":
        play_random(config)
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
    elif args.action in ("apply-colors", "preview-colors"):
        output = args.output or config.get("output", "*")
        profile = {
            **DEFAULT_CONFIG,
            **config.get("assignments", {}).get(output, {}),
            "output": output,
        }
        if args.action == "preview-colors":
            try:
                preview = json.loads(args.settings or "{}")
            except json.JSONDecodeError as error:
                print(f"mpvpaper-engine: réglages JSON invalides : {error}", file=sys.stderr)
                return 2
            profile.update({key: preview[key] for key in COLOR_DEFAULTS if key in preview})
        try:
            apply_colors(profile)
        except (OSError, RuntimeError, json.JSONDecodeError) as error:
            print(f"mpvpaper-engine: {error}", file=sys.stderr)
            return 1
    elif args.action in ("capture", "adapt-theme"):
        output = args.output or config.get("output", "*")
        if not valid_output_name(output):
            print("mpvpaper-engine: nom d’écran invalide", file=sys.stderr)
            return 2
        try:
            profile = {
                **DEFAULT_CONFIG,
                **config.get("assignments", {}).get(output, {}),
                "output": output,
            }
            if args.settings:
                preview = json.loads(args.settings)
                profile.update({key: preview[key] for key in COLOR_DEFAULTS if key in preview})
            if args.action == "adapt-theme":
                frame, integrations = adapt_desktop_theme(
                    output, profile, wallpaper=args.wallpaper,
                )
                print(f"{frame}\t{', '.join(integrations)}")
            else:
                print(capture_wallpaper(output, profile))
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError,
                subprocess.TimeoutExpired) as error:
            print(f"mpvpaper-engine: {error}", file=sys.stderr)
            return 1
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
