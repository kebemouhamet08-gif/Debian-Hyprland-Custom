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

from mpvpaper_engine.config import (
    COLOR_DEFAULTS,
    LEGACY_DEFAULT_CONFIG,
    bounded_number,
    load_legacy_compatible_config,
    normalize_legacy_profile,
    save_legacy_config,
    validate_output_name,
)
from mpvpaper_engine.ipc import EngineClient, EngineIPCError, EngineUnavailableError
from mpvpaper_engine.library import Library
from mpvpaper_engine.paths import EnginePaths
from mpvpaper_engine.state import read_state, state_to_dict


CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "mpvpaper-engine"
CONFIG_FILE = CONFIG_DIR / "config.json"
UNIT_PREFIX = "mpvpaper-engine-wallpaper"
LEGACY_UNIT = f"{UNIT_PREFIX}.service"
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/mpvpaper-engine-{os.getuid()}")) / "mpvpaper-engine"
DEFAULT_CONFIG = dict(LEGACY_DEFAULT_CONFIG)
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".bmp"}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS
WALLPAPER_DIRS = (
    Path.home() / "Pictures" / "Wallpapers" / "Live",
    Path.home() / "Pictures" / "wallpapers",
)


def valid_output_name(value):
    return validate_output_name(value)


def normalize_profile(data, output="*"):
    return normalize_legacy_profile(data, output)


def load_config():
    return load_legacy_compatible_config(CONFIG_FILE)


def save_config(config):
    save_legacy_config(config, CONFIG_FILE)


def _machine_state(state, ok=True, source="engine"):
    return {
        "ok": ok,
        "service": state.get("service_status", "stopped"),
        "source": source,
        "mode": state.get("mode"),
        "updated_at": state.get("updated_at"),
        "outputs": [
            {"output": output, **value}
            for output, value in state.get("outputs", {}).items()
        ],
        "last_error": state.get("last_error"),
    }


def engine_readonly_action(action, output=None, json_output=False):
    paths = EnginePaths.from_environment()
    client = EngineClient(paths, timeout=0.75)
    try:
        if action == "engine-ping":
            result = client.ping()
            payload = {"ok": True, "service": "running", **result}
        else:
            state = client.get_state()
            if output:
                current = client.get_output_state(output)
                state = {**state, "outputs": {output: {
                    key: value for key, value in current.items() if key != "output"
                }}}
            payload = _machine_state(state)
    except EngineUnavailableError as error:
        if action == "current":
            payload = _machine_state(
                state_to_dict(read_state(paths)), ok=False, source="snapshot"
            )
            payload["error"] = str(error)
        else:
            payload = {"ok": False, "service": "unavailable", "error": str(error)}
        if json_output:
            print(json.dumps(payload, separators=(",", ":")))
        else:
            print(f"mpvpaper-engine: {payload['error']}", file=sys.stderr)
        return 3
    except (EngineIPCError, TimeoutError) as error:
        payload = {"ok": False, "service": "error", "error": str(error)}
        if json_output:
            print(json.dumps(payload, separators=(",", ":")))
        else:
            print(f"mpvpaper-engine: {error}", file=sys.stderr)
        return 1

    if json_output:
        print(json.dumps(payload, separators=(",", ":")))
    elif action == "engine-ping":
        print("pong")
    else:
        print(f"{payload['service']}:{len(payload['outputs'])}")
    return 0


def library_list_action(json_output=False):
    try:
        items = Library().list()
        payload = [{
            "id": item.id, "title": item.title, "path": str(item.path),
            "type": item.media_type.value, "width": item.width,
            "height": item.height, "fps": item.fps, "duration": item.duration,
            "favorite": item.favorite, "missing": item.missing,
        } for item in items]
    except (OSError, RuntimeError, ValueError) as error:
        if json_output:
            print(json.dumps({"ok": False, "error": str(error)}, separators=(",", ":")))
        else:
            print(f"mpvpaper-engine: {error}", file=sys.stderr)
        return 1
    if json_output:
        print(json.dumps({"ok": True, "wallpapers": payload}, separators=(",", ":")))
    else:
        for item in payload:
            print(f"{item['id']}\t{item['type']}\t{item['title']}\t{item['path']}")
    return 0


def engine_playback_action(
    action, config, output=None, seconds=None, json_output=False, profile=None
):
    output = output or config.get("output", "*")
    if not valid_output_name(output):
        print("mpvpaper-engine: nom d’écran invalide", file=sys.stderr)
        return 2
    client = EngineClient(timeout=0.75)
    try:
        if action == "pause":
            result = client.pause(output)
        elif action == "resume":
            result = client.resume(output)
        elif action == "toggle":
            result = client.toggle_pause(output)
        elif action == "seek":
            if seconds is None:
                raise ValueError("--seconds est requis pour seek")
            result = client.seek(output, seconds)
        elif action == "restart":
            result = client.restart(output)
        elif action == "profile":
            if profile not in {"auto", "eco", "balanced", "quality"}:
                raise ValueError("--profile auto|eco|balanced|quality est requis")
            result = client.set_performance_profile(output, profile)
        else:
            result = {"outputs": client.list_outputs()}
        payload = {"ok": True, "source": "engine", "output": output, **result}
    except EngineUnavailableError:
        try:
            if action in {"pause", "resume", "toggle"}:
                paused = action == "pause"
                if action == "toggle":
                    paused = not bool(ipc_request(output, ["get_property", "pause"]).get("data"))
                ipc_request(output, ["set_property", "pause", paused])
                result = {"paused": paused}
            elif action == "seek":
                if seconds is None:
                    raise ValueError("--seconds est requis pour seek")
                ipc_request(output, ["seek", float(seconds), "absolute"])
                result = {"position": float(seconds)}
            elif action == "restart":
                run(["systemctl", "--user", "restart", unit_for_output(output)], check=True)
                result = {"restarted": True}
            elif action == "profile":
                raise RuntimeError("le profil nécessite le service Engine v2")
            else:
                result = {"outputs": sorted(config.get("assignments", {}))}
            payload = {"ok": True, "source": "legacy", "output": output, **result}
        except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
            payload = {"ok": False, "source": "legacy", "error": str(error)}
            if json_output:
                print(json.dumps(payload, separators=(",", ":")))
            else:
                print(f"mpvpaper-engine: {error}", file=sys.stderr)
            return 1
    except (EngineIPCError, TimeoutError, ValueError) as error:
        payload = {"ok": False, "source": "engine", "error": str(error)}
        if json_output:
            print(json.dumps(payload, separators=(",", ":")))
        else:
            print(f"mpvpaper-engine: {error}", file=sys.stderr)
        return 1
    if json_output:
        print(json.dumps(payload, separators=(",", ":")))
    elif action == "outputs":
        print("\n".join(payload["outputs"]))
    else:
        print(json.dumps(result, separators=(",", ":")))
    return 0


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


def video_duration(source):
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(source),
    ], capture_output=True, text=True, timeout=8, check=False)
    try:
        return max(0.1, float(result.stdout.strip()))
    except (TypeError, ValueError):
        return 0.0


def capture_palette_source(source, output, config):
    """Compose quatre instants de la vidéo pour obtenir une palette plus stable."""
    source = Path(source).expanduser()
    if not source.is_file() or source.suffix.lower() not in VIDEO_EXTENSIONS:
        raise RuntimeError("le fond vidéo choisi est introuvable ou non pris en charge")
    duration = video_duration(source)
    if not duration:
        return capture_source_wallpaper(source, output, config)

    base = capture_path(output)
    destination = base.with_name(f"{base.stem}-theme.png")
    temporary = destination.with_name(f".{destination.stem}.new.png")
    positions = [duration * ratio for ratio in (0.12, 0.37, 0.62, 0.87)]
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for position in positions:
        command.extend(["-ss", f"{position:.3f}", "-i", str(source)])
    filters = []
    rendered = capture_filter(config)
    for index in range(4):
        filters.append(
            f"[{index}:v]scale=480:270:force_original_aspect_ratio=increase,"
            f"crop=480:270,{rendered}[v{index}]"
        )
    filters.append(
        "[v0][v1][v2][v3]xstack=inputs=4:"
        "layout=0_0|w0_0|0_h0|w0_h0[out]"
    )
    command.extend([
        "-filter_complex", ";".join(filters), "-map", "[out]",
        "-frames:v", "1", str(temporary),
    ])
    result = subprocess.run(
        command, capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode != 0 or not temporary.is_file() or not temporary.stat().st_size:
        temporary.unlink(missing_ok=True)
        return capture_source_wallpaper(source, output, config, duration * 0.5)
    temporary.replace(destination)
    destination.chmod(0o600)
    return destination


def adapt_desktop_theme(output, config, wallpaper=None):
    """Génère les palettes du bureau depuis une frame, sans remplacer le fond vidéo."""
    frame = (capture_palette_source(wallpaper, output, config)
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
            [str(nova_script), "--noswitch", "--image", str(frame),
             "--type", "scheme-tonal-spot"],
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
        "load-scripts=no", "terminal=no",
        f"speed={config['speed']}",
        f"input-ipc-server={ipc_socket}",
        *(f"{name}={int(config.get(name, 0))}" for name in (
            "brightness", "contrast", "gamma", "saturation", "hue"
        )),
        f"vf={color_filter(config)}",
    ]
    fit_options = {
        "cover": ["video-unscaled=no", "keepaspect=yes", "panscan=1.0"],
        "contain": ["video-unscaled=no", "keepaspect=yes", "panscan=0.0"],
        "stretch": ["video-unscaled=no", "keepaspect=no", "panscan=0.0"],
    }
    options.extend(fit_options.get(config.get("fit_mode"), fit_options["cover"]))
    if config["loop"]:
        options.append("loop-file=inf")
    options.extend(["image-display-duration=inf", "keep-open=yes"])
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
        raise SystemExit(f"Fond introuvable : {wallpaper}")
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
            if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS:
                resolved = path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    wallpapers.append(path)
    return wallpapers


def play_random(config):
    wallpapers = random_wallpapers()
    if not wallpapers:
        locations = ", ".join(str(path) for path in WALLPAPER_DIRS)
        raise SystemExit(f"Aucun fond image ou vidéo trouvé dans : {locations}")

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
        "capture", "adapt-theme", "engine-ping", "current", "pause", "resume",
        "toggle", "seek", "restart", "outputs",
        "list", "profile",
    ))
    parser.add_argument("--output", default=None, help="écran ciblé pour les couleurs")
    parser.add_argument("--settings", default=None, help="réglages couleur JSON à prévisualiser")
    parser.add_argument("--wallpaper", default=None, help="fond vidéo choisi pour la palette")
    parser.add_argument("--json", action="store_true", help="sortie JSON sans texte additionnel")
    parser.add_argument("--seconds", type=float, default=None, help="position absolue en secondes")
    parser.add_argument("--profile", default=None, help="profil auto, eco, balanced ou quality")
    args = parser.parse_args()
    if args.action in {"engine-ping", "current", "status"}:
        return engine_readonly_action(args.action, args.output, args.json)
    if args.action == "list":
        return library_list_action(args.json)
    config = load_config()
    if args.action in {"pause", "resume", "toggle", "seek", "restart", "outputs", "profile"}:
        return engine_playback_action(
            args.action, config, args.output, args.seconds, args.json, args.profile
        )

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
