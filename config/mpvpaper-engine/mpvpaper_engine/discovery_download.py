"""Downloads selected Discover pages into the local wallpaper library."""

from __future__ import annotations

from html.parser import HTMLParser
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from mpvpaper_download import (
    DownloadOutcome,
    IMAGE_EXTENSIONS,
    MEDIA_EXTENSIONS,
    VIDEO_EXTENSIONS,
    adapt_image_to_height,
    detect_hardware_profile,
    downloader_diagnostics,
    force_steam_workshop_download,
    requested_height,
    steam_workshop_id,
    youtube_download_command,
)


MAX_PAGE_BYTES = 4 * 1024 * 1024
MAX_MEDIA_BYTES = 8 * 1024 * 1024 * 1024


class _MediaLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        candidates = []
        if tag == "a":
            candidates.append(values.get("href", ""))
        elif tag in {"img", "source", "video"}:
            candidates.extend((values.get("src", ""), values.get("data-src", "")))
            candidates.extend(
                value.strip().split(" ", 1)[0]
                for value in values.get("srcset", "").split(",") if value.strip()
            )
        for value in candidates:
            path = urlparse(value).path.casefold()
            if "/dl/" in path or Path(path).suffix in MEDIA_EXTENSIONS:
                self.links.append(value)


class DiscoveryDownloader:
    def __init__(self, library_dir: Path):
        self.library_dir = Path(library_dir)

    def profile(self):
        return detect_hardware_profile()

    def diagnostics(self):
        return {**downloader_diagnostics(), "profile": self.profile()}

    def download(self, uri: str, title: str, selected_height: int = 0,
                 *, firefox=False) -> DownloadOutcome:
        profile = self.profile()
        height = requested_height(selected_height, profile)
        if steam_workshop_id(uri):
            return force_steam_workshop_download(uri, self.library_dir, height)
        media_uri = self._page_media(uri, height)
        suffix = Path(urlparse(media_uri).path).suffix.casefold()
        if suffix in MEDIA_EXTENSIONS:
            path = self._direct(media_uri, title, suffix)
            if suffix in IMAGE_EXTENSIONS:
                path = adapt_image_to_height(path, height)
            return DownloadOutcome(path, f"Média téléchargé · cible {height}p", "direct")
        return self._yt_dlp(media_uri, title, height, firefox=firefox)

    def _page_media(self, uri: str, target_height: int) -> str:
        if Path(urlparse(uri).path).suffix.casefold() in MEDIA_EXTENSIONS:
            return uri
        try:
            request = Request(uri, headers={"User-Agent": "Mozilla/5.0 MPVpaperEngine/2"})
            with urlopen(request, timeout=20) as response:
                contents = response.read(MAX_PAGE_BYTES + 1)
            if len(contents) > MAX_PAGE_BYTES:
                return uri
            parser = _MediaLinks()
            parser.feed(contents.decode("utf-8", "replace"))
            links = {urljoin(uri, link) for link in parser.links}
            if links:
                return max(links, key=lambda link: self._link_rank(link, target_height))
        except (OSError, ValueError):
            pass
        return uri

    @staticmethod
    def _link_rank(uri: str, target_height: int):
        lowered = uri.casefold()
        resolution = 0
        for token, height in (("8k", 4320), ("4k", 2160), ("1440", 1440),
                              ("1080", 1080), ("720", 720)):
            if token in lowered:
                resolution = height
                break
        within_target = resolution <= target_height
        is_video = Path(urlparse(uri).path).suffix.casefold() in VIDEO_EXTENSIONS
        return within_target, resolution if within_target else -resolution, is_video

    def _direct(self, uri: str, title: str, suffix: str) -> Path:
        self.library_dir.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", title).strip(" ._")[:150]
        stem = stem or "wallpaper"
        destination = self.library_dir / f"{stem}{suffix}"
        counter = 2
        while destination.exists():
            destination = self.library_dir / f"{stem}-{counter}{suffix}"
            counter += 1
        partial = destination.with_name(f".{destination.name}.part")
        request = Request(uri, headers={"User-Agent": "Mozilla/5.0 MPVpaperEngine/2"})
        total = 0
        try:
            with urlopen(request, timeout=45) as response, partial.open("wb") as stream:
                while block := response.read(1024 * 1024):
                    total += len(block)
                    if total > MAX_MEDIA_BYTES:
                        raise ValueError("média distant trop volumineux")
                    stream.write(block)
            os.replace(partial, destination)
        finally:
            partial.unlink(missing_ok=True)
        return destination

    def _yt_dlp(self, uri: str, title: str, height: int,
                *, firefox=False) -> DownloadOutcome:
        self.library_dir.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", title).strip(" ._")[:150]
        try:
            command = youtube_download_command(
                uri, self.library_dir / f"{stem or '%(title).150B'}.%(ext)s",
                height, firefox=firefox,
            )
        except FileNotFoundError as error:
            return DownloadOutcome(None, str(error), "yt-dlp")
        try:
            result = subprocess.run(command, capture_output=True, text=True,
                                    timeout=1800, check=False)
        except subprocess.TimeoutExpired:
            return DownloadOutcome(None, "téléchargement interrompu après 30 minutes", "yt-dlp")
        except OSError as error:
            return DownloadOutcome(None, str(error), "yt-dlp")
        paths = [Path(line) for line in result.stdout.splitlines() if line.strip()]
        path = paths[-1] if result.returncode == 0 and paths else None
        if path is not None and path.is_file():
            return DownloadOutcome(path, f"Vidéo téléchargée · cible {height}p", "yt-dlp")
        detail = result.stderr.strip().splitlines()
        message = "\n".join(detail[-8:]) if detail else "aucun média détecté"
        lowered = message.casefold()
        source = "authentication-required" if any(token in lowered for token in (
            "sign in", "not a bot", "cookies", "http error 403", "page needs to be reloaded",
        )) else "yt-dlp"
        return DownloadOutcome(None, message, source)
