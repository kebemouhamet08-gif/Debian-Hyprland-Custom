#!/usr/bin/env python3

"""Politique de qualité et import Steam Workshop pour MPVpaper Engine."""

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


WALLPAPER_ENGINE_APP_ID = "431960"
STEAM_DETAILS_API = (
    "https://api.steampowered.com/ISteamRemoteStorage/"
    "GetPublishedFileDetails/v1/"
)
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".bmp"}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS
ENGINE_DIR = Path(__file__).resolve().parent
PRIVATE_PYTHON = ENGINE_DIR / ".venv" / "bin" / "python"
LOCAL_YTDLP = Path.home() / ".local" / "bin" / "yt-dlp"
LOCAL_DENO = Path.home() / ".local" / "bin" / "deno"
QUALITY_CHOICES = (
    ("Automatique (machine)", 0),
    ("1080p", 1080),
    ("1440p", 1440),
    ("2160p (4K)", 2160),
    ("4320p (8K)", 4320),
)


@dataclass(frozen=True)
class HardwareProfile:
    target_height: int
    display_height: int
    memory_gib: int
    gpu: str
    reason: str


@dataclass(frozen=True)
class DownloadOutcome:
    path: Path | None
    message: str
    source: str


def _command_text(command, timeout=4):
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip()


def _monitor_heights():
    raw = _command_text(["hyprctl", "monitors", "all", "-j"])
    if raw:
        try:
            return [int(item.get("height", 0)) for item in json.loads(raw)]
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
    heights = []
    for modes in Path("/sys/class/drm").glob("card*-*/modes"):
        try:
            for line in modes.read_text(encoding="utf-8").splitlines():
                match = re.fullmatch(r"\d+x(\d+)", line.strip())
                if match:
                    heights.append(int(match.group(1)))
                    break
        except OSError:
            continue
    return heights


def _memory_kib():
    try:
        match = re.search(
            r"^MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text(), re.MULTILINE
        )
        return int(match.group(1)) if match else 0
    except OSError:
        return 0


def choose_hardware_profile(heights, memory_kib, gpu_text):
    display_height = max([int(value) for value in heights if int(value) > 0] or [1080])
    memory_gib = max(1, round(memory_kib / 1024 / 1024))
    gpu = (gpu_text or "GPU non détecté").strip()
    lowered = gpu.casefold()
    discrete = any(name in lowered for name in ("nvidia", "geforce", "radeon", "amd"))
    modern_integrated = any(name in lowered for name in ("intel arc", "iris xe", "780m", "680m"))

    if display_height <= 1080:
        display_target = 1080
    elif display_height <= 1440:
        display_target = 1440
    elif display_height <= 2160:
        display_target = 2160
    else:
        display_target = 4320

    if memory_gib >= 24 and discrete:
        hardware_cap = 4320
    elif memory_gib >= 12 and (discrete or modern_integrated):
        hardware_cap = 2160
    elif memory_gib >= 8:
        hardware_cap = 1440
    else:
        hardware_cap = 1080
    target = min(display_target, hardware_cap)
    reason = (
        f"écran {display_height}p, {memory_gib} Gio RAM, "
        f"plafond matériel {hardware_cap}p"
    )
    return HardwareProfile(target, display_height, memory_gib, gpu, reason)


def detect_hardware_profile():
    gpu = _command_text(["lspci"])
    gpu_lines = [line for line in gpu.splitlines()
                 if re.search(r"VGA|3D|Display", line, re.IGNORECASE)]
    return choose_hardware_profile(_monitor_heights(), _memory_kib(), " · ".join(gpu_lines))


def requested_height(selected_height, profile=None):
    return int(selected_height) or (profile or detect_hardware_profile()).target_height


def ytdlp_command_prefix():
    """Prefer the engine-owned environment without breaking existing installs."""
    if PRIVATE_PYTHON.is_file():
        return [str(PRIVATE_PYTHON), "-m", "yt_dlp"]
    if LOCAL_YTDLP.is_file():
        return [str(LOCAL_YTDLP)]
    executable = shutil.which("yt-dlp")
    return [executable] if executable else []


def youtube_download_command(uri, output_template, height, *, firefox=False):
    prefix = ytdlp_command_prefix()
    if not prefix:
        raise FileNotFoundError("yt-dlp est introuvable")
    command = [
        *prefix, "--no-playlist", "--no-progress", "--continue",
        "--retries", "10", "--fragment-retries", "10",
        "--file-access-retries", "5",
        "--retry-sleep", "http:exp=1:20",
        "--retry-sleep", "fragment:exp=1:20",
        "-f", f"bv*[height<={int(height)}]+ba/b[height<={int(height)}]",
        "--merge-output-format", "mp4", "--remux-video", "mp4",
        "--print", "after_move:filepath", "-o", str(output_template),
    ]
    deno = LOCAL_DENO if LOCAL_DENO.is_file() else None
    if deno is not None:
        command.extend(["--js-runtimes", f"deno:{deno}"])
    if firefox:
        command.extend(["--cookies-from-browser", "firefox"])
    command.append(uri)
    return command


def downloader_diagnostics():
    prefix = ytdlp_command_prefix()
    version = _command_text([*prefix, "--version"], timeout=8) if prefix else ""
    deno_version = _command_text([str(LOCAL_DENO), "--version"], timeout=5) \
        if LOCAL_DENO.is_file() else ""
    ffmpeg = shutil.which("ffmpeg")
    firefox_profiles = Path.home() / ".mozilla" / "firefox"
    return {
        "yt_dlp": bool(prefix and version),
        "yt_dlp_version": version.splitlines()[0] if version else "indisponible",
        "private_environment": bool(PRIVATE_PYTHON.is_file()),
        "deno": bool(deno_version),
        "deno_version": deno_version.splitlines()[0] if deno_version else "indisponible",
        "ffmpeg": bool(ffmpeg),
        "firefox_session": firefox_profiles.is_dir(),
    }


def steam_workshop_id(uri):
    try:
        parsed = urlparse(uri)
    except ValueError:
        return ""
    if parsed.hostname not in {"steamcommunity.com", "www.steamcommunity.com"}:
        return ""
    match = re.search(r"(?:^|&)id=([1-9]\d*)(?:&|$)", parsed.query)
    return match.group(1) if match else ""


def steam_file_details(item_id, opener=urlopen):
    body = urlencode({"itemcount": "1", "publishedfileids[0]": item_id}).encode()
    request = Request(
        STEAM_DETAILS_API, data=body,
        headers={"User-Agent": "MPVpaperEngine/2", "Content-Type": "application/x-www-form-urlencoded"},
    )
    with opener(request, timeout=20) as response:
        payload = response.read(2 * 1024 * 1024 + 1)
    if len(payload) > 2 * 1024 * 1024:
        raise ValueError("réponse Steam trop volumineuse")
    data = json.loads(payload)
    details = data.get("response", {}).get("publishedfiledetails", [])
    if not details or str(details[0].get("publishedfileid", "")) != item_id:
        raise ValueError("fiche Steam Workshop introuvable")
    return details[0]


def steam_library_roots(home=None):
    home = Path(home or Path.home())
    roots = [home / ".local/share/Steam", home / ".steam/steam", home / ".steam/root"]
    discovered = []
    for root in roots:
        if root.exists():
            discovered.append(root.resolve())
        manifest = root / "steamapps/libraryfolders.vdf"
        try:
            text = manifest.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for value in re.findall(r'"path"\s+"([^"]+)"', text):
            path = Path(value.replace("\\\\", "\\"))
            if path.exists():
                discovered.append(path.resolve())
    return list(dict.fromkeys(discovered))


def find_workshop_item(item_id, roots=None):
    for root in roots or steam_library_roots():
        candidate = root / "steamapps/workshop/content" / WALLPAPER_ENGINE_APP_ID / item_id
        if candidate.is_dir():
            return candidate
    return None


def _safe_title(value, fallback):
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", value or "").strip(" ._")
    return (cleaned[:120] or fallback)


def _project_media(item_dir):
    try:
        project = json.loads((item_dir / "project.json").read_text(encoding="utf-8"))
        relative = project.get("file", "")
        candidate = (item_dir / relative).resolve()
        if candidate.is_relative_to(item_dir.resolve()) and candidate.is_file():
            return candidate
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    candidates = [
        path for path in item_dir.rglob("*")
        if path.is_file() and path.suffix.casefold() in MEDIA_EXTENSIONS
    ]
    return max(candidates, key=lambda path: path.stat().st_size) if candidates else None


def import_workshop_item(item_dir, library_dir, item_id, title=""):
    media = _project_media(item_dir)
    if media is None:
        return None
    library_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_title(title, f"Steam Workshop {item_id}")
    destination = library_dir / f"{stem} [Steam-{item_id}]{media.suffix.casefold()}"
    if not destination.exists() or destination.stat().st_size != media.stat().st_size:
        shutil.copy2(media, destination)
    return destination


def adapt_image_to_height(path, target_height, runner=subprocess.run):
    path = Path(path)
    if path.suffix.casefold() not in IMAGE_EXTENSIONS or target_height <= 0:
        return path
    try:
        probe = runner(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=height", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=20, check=False,
        )
        height = int((json.loads(probe.stdout).get("streams") or [{}])[0].get("height", 0))
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return path
    if height <= target_height or probe.returncode != 0:
        return path
    destination = path.with_name(f"{path.stem}-{target_height}p{path.suffix.casefold()}")
    result = runner(
        ["ffmpeg", "-y", "-i", str(path), "-vf", f"scale=-2:{target_height}",
         "-frames:v", "1", str(destination)],
        capture_output=True, text=True, timeout=600, check=False,
    )
    return destination if result.returncode == 0 and destination.is_file() else path


def media_dimensions(path, runner=subprocess.run):
    try:
        result = runner(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=20, check=False,
        )
        stream = (json.loads(result.stdout).get("streams") or [{}])[0]
        return int(stream.get("width", 0)), int(stream.get("height", 0))
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return 0, 0


def _download(url, destination, maximum_bytes):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 MPVpaperEngine/2"})
    temporary = destination.with_name(f".{destination.name}.part")
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with urlopen(request, timeout=45) as response, temporary.open("wb") as stream:
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > maximum_bytes:
                    raise ValueError("fichier distant trop volumineux")
                stream.write(block)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _direct_destination(details, item_id, library_dir, url, preview=False):
    title = _safe_title(details.get("title", ""), f"Steam Workshop {item_id}")
    suffix = Path(str(details.get("filename") or urlparse(url).path)).suffix.casefold()
    if suffix not in MEDIA_EXTENSIONS:
        suffix = ".jpg" if preview else ".bin"
    marker = "preview" if preview else "file"
    return library_dir / f"{title} [Steam-{item_id}-{marker}]{suffix}"


def _import_downloaded_archive(archive, library_dir, item_id, title):
    try:
        is_zip = zipfile.is_zipfile(archive)
    except OSError:
        return None
    if not is_zip:
        return None
    with tempfile.TemporaryDirectory(prefix="mpvpaper-steam-") as directory:
        root = Path(directory).resolve()
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                target = (root / member.filename).resolve()
                if not target.is_relative_to(root):
                    raise ValueError("archive Workshop non sûre")
            bundle.extractall(root)
        return import_workshop_item(root, library_dir, item_id, title)


def force_steam_workshop_download(uri, library_dir, target_height, runner=subprocess.run):
    item_id = steam_workshop_id(uri)
    if not item_id:
        return DownloadOutcome(None, "Adresse Steam Workshop invalide", "steam")
    library_dir = Path(library_dir)
    local = find_workshop_item(item_id)
    if local:
        imported = import_workshop_item(local, library_dir, item_id)
        if imported:
            imported = adapt_image_to_height(imported, target_height)
            return DownloadOutcome(
                imported, f"Contenu Steam local importé ({target_height}p cible)", "local"
            )
    details = {}
    try:
        details = steam_file_details(item_id)
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    title = str(details.get("title") or "")
    file_url = str(details.get("file_url") or "")
    if file_url and urlparse(file_url).scheme == "https":
        destination = _direct_destination(details, item_id, library_dir, file_url)
        try:
            _download(file_url, destination, 8 * 1024 * 1024 * 1024)
            if destination.suffix.casefold() in MEDIA_EXTENSIONS:
                destination = adapt_image_to_height(destination, target_height)
                return DownloadOutcome(destination, "Fichier Workshop téléchargé directement", "steam-api")
            imported = _import_downloaded_archive(destination, library_dir, item_id, title)
            if imported:
                imported = adapt_image_to_height(imported, target_height)
                destination.unlink(missing_ok=True)
                return DownloadOutcome(imported, "Archive Workshop téléchargée et extraite", "steam-api")
            destination.unlink(missing_ok=True)
        except (OSError, ValueError):
            destination.unlink(missing_ok=True)

    steamcmd = shutil.which("steamcmd")
    if steamcmd:
        command = [
            steamcmd, "+login", "anonymous", "+workshop_download_item",
            WALLPAPER_ENGINE_APP_ID, item_id, "validate", "+quit",
        ]
        try:
            result = runner(command, capture_output=True, text=True, timeout=1800, check=False)
        except (OSError, subprocess.TimeoutExpired):
            result = None
        paths = [] if result is None else re.findall(r'(?i)downloaded item \d+ to "([^"]+)"', result.stdout)
        local = Path(paths[-1]) if paths else find_workshop_item(item_id)
        if local and local.is_dir():
            imported = import_workshop_item(local, library_dir, item_id, title)
            if imported:
                imported = adapt_image_to_height(imported, target_height)
                return DownloadOutcome(imported, "Téléchargement forcé par steamcmd", "steamcmd")

    preview_url = str(details.get("preview_url") or "")
    if preview_url and urlparse(preview_url).scheme == "https":
        destination = _direct_destination(details, item_id, library_dir, preview_url, preview=True)
        try:
            _download(preview_url, destination, 128 * 1024 * 1024)
            width, height = media_dimensions(destination)
            minimum = min(1080, max(720, target_height // 2))
            if max(width, height) < minimum:
                destination.unlink(missing_ok=True)
                return DownloadOutcome(
                    None,
                    f"Steam ne fournit qu’une miniature {width}×{height}; "
                    "le projet complet exige Steam/Wallpaper Engine ou steamcmd authentifié.",
                    "preview",
                )
            destination = adapt_image_to_height(destination, target_height)
            return DownloadOutcome(
                destination,
                "Projet Scene/Web non exportable : aperçu Steam importé comme image",
                "preview",
            )
        except (OSError, ValueError):
            destination.unlink(missing_ok=True)
    return DownloadOutcome(
        None,
        "Steam n’expose aucun média importable. Installez steamcmd ou abonnez-vous à l’élément dans Steam.",
        "steam",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Télécharger ou importer de force un fond Steam Workshop"
    )
    parser.add_argument("uri", nargs="?", help="URL de la fiche Steam Workshop")
    parser.add_argument(
        "--quality", choices=("auto", "1080", "1440", "2160", "4320"),
        default="auto", help="résolution cible (auto par défaut)",
    )
    parser.add_argument(
        "--library", type=Path, default=Path.home() / "Pictures/Wallpapers/Live",
        help="bibliothèque de destination",
    )
    parser.add_argument("--profile", action="store_true", help="afficher le profil matériel")
    args = parser.parse_args(argv)
    profile = detect_hardware_profile()
    if args.profile:
        print(f"{profile.target_height}p automatique — {profile.reason}")
        if not args.uri:
            return 0
    if not args.uri:
        parser.error("une URL Steam Workshop est requise")
    height = profile.target_height if args.quality == "auto" else int(args.quality)
    outcome = force_steam_workshop_download(args.uri, args.library, height)
    print(outcome.message)
    if outcome.path:
        print(outcome.path)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
