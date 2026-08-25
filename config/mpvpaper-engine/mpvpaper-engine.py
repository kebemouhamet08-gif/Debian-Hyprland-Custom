#!/usr/bin/env python3

import configparser
import fcntl
import hashlib
from html.parser import HTMLParser
import io
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import tempfile
from urllib.parse import parse_qs, quote_plus, urljoin
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, WebKit


APP_ID = "io.github.kebemouhamet08.MPVpaperEngine"
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"}
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "mpvpaper-engine"
CONFIG_FILE = CONFIG_DIR / "config.json"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "mpvpaper-engine" / "thumbnails"
METADATA_FILE = CACHE_DIR.parent / "metadata.json"
TASTE_DB = CONFIG_DIR / "suggestions.db"
SUGGESTION_CACHE = CACHE_DIR.parent / "suggestions"
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/mpvpaper-engine-{os.getuid()}"))
SUGGESTION_HISTORY_FILE = RUNTIME_DIR / "suggestion-history.json"
SUGGESTION_COOLDOWN = 12
EXPLORATION_RATE = 0.15
SOURCE_REFRESH_INTERVAL = 30
SOURCE_FRONTIER_FILE = CONFIG_DIR / "source-frontier.json"
SOURCE_FRONTIER_LOCK = CONFIG_DIR / "source-frontier.lock"
SOURCE_FRONTIER_VERSION = 2
SOURCE_CRAWL_SLICE = 8
LIBRARY_DIR = Path.home() / "Pictures" / "Wallpapers" / "Live"
LEGACY_LIBRARY_DIR = Path.home() / "Pictures" / "wallpapers"
CONTROLLER = Path.home() / ".local" / "lib" / "mpvpaper-engine" / "mpvpaper-enginectl.py"
V2_INSTALLER = Path(os.environ.get(
    "DEBIAN_V2_INSTALLER", Path.home() / "Debian-Hyprland-Custom" / "install-v2.sh"
))
V2_THEME_MANIFEST = V2_INSTALLER.parent / "config" / "v2" / "themes.tsv"
SDDM_INSTALLER = Path.home() / ".local" / "lib" / "mpvpaper-engine" / "install-sddm-background.sh"
LOCAL_YTDLP = Path.home() / ".local" / "bin" / "yt-dlp"
DEFAULT_CONFIG = {
    "wallpaper": "", "output": "*", "volume": 0, "speed": 1.0,
    "loop": True, "hardware_decode": True, "auto_pause": True, "autostart": True,
    "brightness": 0, "contrast": 0, "gamma": 0, "saturation": 0, "hue": 0,
    "temperature": 6500,
    "red_balance": 0, "green_balance": 0, "blue_balance": 0,
}
COLOR_DEFAULTS = {
    key: DEFAULT_CONFIG[key] for key in (
        "brightness", "contrast", "gamma", "saturation", "hue",
        "temperature", "red_balance", "green_balance", "blue_balance",
    )
}
COLOR_PRESETS = {
    "Original": COLOR_DEFAULTS,
    "Bureau": {**COLOR_DEFAULTS, "contrast": 5, "saturation": 5},
    "Nuit": {**COLOR_DEFAULTS, "brightness": -15, "gamma": -8,
             "saturation": -8, "temperature": 4000},
    "Photo": {**COLOR_DEFAULTS, "contrast": 8, "saturation": 12},
    "Gaming": {**COLOR_DEFAULTS, "contrast": 15, "saturation": 20, "gamma": 5},
}
WALLPAPER_SOURCES = {
    "Steam Workshop": "https://steamcommunity.com/workshop/browse?appid=431960",
    "YouTube · TeshiiSan": "https://www.youtube.com/@TeshiiSan/videos",
    "MotionBGS": "https://motionbgs.com/",
    "MoeWalls": "https://moewalls.com/",
    "VSThemes": "https://vsthemes.org/en/wallpapers/",
}
DEFAULT_SUGGESTIONS = (
    ("https://steamcommunity.com/sharedfiles/filedetails/?id=2704773569", "[4K] CITRUS - go to class", "steamcommunity.com", "anime scene 4k popular"),
    ("https://steamcommunity.com/sharedfiles/filedetails/?id=1579461169", "Top 50 New Wallpapers", "steamcommunity.com", "collection popular community"),
    ("https://motionbgs.com/brain-interface", "Brain Interface Live Wallpaper", "motionbgs.com", "technology sci-fi minimal"),
    ("https://motionbgs.com/cyberpunk-tokyo-city", "Cyberpunk Tokyo City Live Wallpaper", "motionbgs.com", "cyberpunk city games"),
    ("https://motionbgs.com/chihiro-spirited-away", "Chihiro Spirited Away Live Wallpaper", "motionbgs.com", "anime fantasy"),
    ("https://motionbgs.com/frieren-minimal-art", "Frieren Minimal Art Live Wallpaper", "motionbgs.com", "anime minimal black white"),
    ("https://motionbgs.com/bmw-m4-black", "BMW M4 Black Live Wallpaper", "motionbgs.com", "car bmw dark"),
    ("https://motionbgs.com/summer-mountain-paradise", "Summer Mountain Paradise Live Wallpaper", "motionbgs.com", "nature mountain landscape"),
    ("https://motionbgs.com/edge-of-the-universe", "Edge of the Universe Live Wallpaper", "motionbgs.com", "space universe sci-fi"),
    ("https://moewalls.com/lifestyle/lofi-house-cloudy-day-live-wallpaper/", "Lofi House Cloudy Day Live Wallpaper", "moewalls.com", "lofi landscape peaceful"),
    ("https://moewalls.com/anime/flowers-water-stream-ghibli-live-wallpaper/", "Flowers Water Stream Ghibli Live Wallpaper", "moewalls.com", "anime nature ghibli"),
    ("https://moewalls.com/lifestyle/chillout-beach-live-wallpaper/", "Chillout Beach Live Wallpaper", "moewalls.com", "beach water tropical"),
)
LEGACY_CATALOG_PAGES = (
    "https://vsthemes.org/en/wallpapers/page/4/",
)
YOUTUBE_FEATURED = (
    ("https://www.youtube.com/watch?v=Z1TlGcjJWNU", "Bounce It Mavuika!", "youtube.com",
     "teshiilatte mavuika genshin animation dance popular", 6401395, 55177),
    ("https://www.youtube.com/watch?v=QxKwL_TlmP4", "Furina Funky Chemicals!", "youtube.com",
     "teshiilatte furina genshin animation dance popular", 1079702, 25593),
)
LEGACY_YOUTUBE_FEATURED = (
    "https://www.youtube.com/watch?v=fmN1RaWO9lc",
    "https://www.youtube.com/watch?v=DEMaBg779gs",
)
AD_DOMAINS = (
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "adservice.google.com", "amazon-adsystem.com", "adnxs.com", "criteo.com",
    "criteo.net", "taboola.com", "outbrain.com", "popads.net", "popcash.net",
    "propellerads.com", "exoclick.com", "juicyads.com", "trafficjunky.net",
)
ADBLOCK_CSS = """
    .adsbygoogle, .advertisement, .ad-container, .ad-wrapper, [data-ad-slot],
    [id^="google_ads"], [id^="div-gpt-ad"], iframe[src*="doubleclick.net"],
    iframe[src*="googlesyndication.com"], [class*="popup-ad"] {
        display: none !important; visibility: hidden !important;
    }
"""


def atomic_write_text(destination, contents, mode=0o600):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=f".{destination.name}-", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(mode)
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


TAG_STOPWORDS = {
    "wallpaper", "live", "animated", "background", "video", "fond", "ecran",
    "the", "and", "for", "with", "from", "page", "https", "www", "com",
    "motionbgs", "moewalls", "vsthemes", "html", "en",
}


def content_tags(*values):
    words = re.findall(r"[a-z0-9]+", " ".join(values).casefold())
    return sorted({word for word in words if len(word) > 2 and word not in TAG_STOPWORDS})[:16]


def content_fingerprint(uri, title=""):
    parsed = urlparse(uri)
    query = dict(item.split("=", 1) for item in parsed.query.split("&") if "=" in item)
    host = parsed.netloc.casefold().removeprefix("www.")
    if host in {"youtube.com", "m.youtube.com"} and query.get("v"):
        return "youtube:" + query["v"]
    if host == "youtu.be" and parsed.path.strip("/"):
        return "youtube:" + parsed.path.strip("/").split("/", 1)[0]
    if "steamcommunity.com" in host and query.get("id"):
        return "steam:" + query["id"]
    generic = {
        "live", "wallpaper", "animated", "animation", "video", "background",
        "fond", "ecran", "4k", "uhd", "hd", "official",
    }
    words = [word for word in re.findall(r"[a-z0-9]+", title.casefold())
             if len(word) > 2 and word not in generic]
    if words:
        return "title:" + "-".join(words[:12])
    canonical_path = re.sub(r"/+", "/", parsed.path.casefold()).rstrip("/")
    return f"url:{host}{canonical_path}"


def is_youtube_url(value):
    try:
        host = urlparse(value).netloc.casefold().split(":", 1)[0]
    except ValueError:
        return False
    return host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def youtube_download_command(uri, height):
    command = [
        str(LOCAL_YTDLP) if LOCAL_YTDLP.is_file() else "yt-dlp",
        "--no-playlist", "--no-progress",
        "-f", f"bv*[height<={height}]+ba/b[height<={height}]",
        "--merge-output-format", "mp4", "--remux-video", "mp4",
        "--print", "after_move:filepath",
        "-o", str(LIBRARY_DIR / "%(title).160B [YouTube]-%(id)s.%(ext)s"),
        uri,
    ]
    return command


def installed_appearance_items(kind):
    if kind == "gtk":
        roots = (Path("/usr/share/themes"), Path.home() / ".themes",
                 Path.home() / ".local/share/themes")
        markers = ("gtk-3.0", "gtk-4.0")
    else:
        roots = (Path("/usr/share/icons"), Path.home() / ".icons",
                 Path.home() / ".local/share/icons")
        markers = ("index.theme",) if kind == "icons" else ("cursors",)
    names = set()
    for root in roots:
        if not root.is_dir():
            continue
        for item in root.iterdir():
            if item.is_dir() and any((item / marker).exists() for marker in markers):
                names.add(item.name)
    return sorted(names, key=str.casefold)


def v2_themes():
    themes = []
    try:
        lines = V2_THEME_MANIFEST.read_text(encoding="utf-8").splitlines()
    except OSError:
        return themes
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) >= 4:
            themes.append((fields[0], fields[2], fields[3]))
    return themes


def desktop_interface_setting(key, fallback=""):
    try:
        return Gio.Settings.new("org.gnome.desktop.interface").get_string(key)
    except GLib.Error:
        return fallback


def write_gtk_theme_settings(values, dark):
    for version in ("gtk-3.0", "gtk-4.0"):
        settings_dir = Path.home() / ".config" / version
        settings_file = settings_dir / "settings.ini"
        parser = configparser.ConfigParser()
        if settings_file.is_file():
            parser.read(settings_file, encoding="utf-8")
        if not parser.has_section("Settings"):
            parser.add_section("Settings")
        section = parser["Settings"]
        section["gtk-theme-name"] = values["gtk-theme"]
        section["gtk-icon-theme-name"] = values["icon-theme"]
        section["gtk-cursor-theme-name"] = values["cursor-theme"]
        section["gtk-application-prefer-dark-theme"] = "true" if dark else "false"
        if version == "gtk-4.0":
            section.pop("gtk-modules", None)
        serialized = io.StringIO()
        parser.write(serialized)
        atomic_write_text(settings_file, serialized.getvalue())


class TasteStore:
    def __init__(self, path=TASTE_DB):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.execute("PRAGMA cache_size=-2000")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS candidates (
                uri TEXT PRIMARY KEY, title TEXT NOT NULL, source TEXT NOT NULL,
                tags TEXT NOT NULL, score REAL NOT NULL DEFAULT 0,
                views INTEGER NOT NULL DEFAULT 0, last_seen INTEGER NOT NULL,
                external_views INTEGER NOT NULL DEFAULT 0,
                external_likes INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS tag_profile (
                tag TEXT PRIMARY KEY, weight REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS suggestion_impressions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, uri TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS suggestion_seen (
                fingerprint TEXT PRIMARY KEY, uri TEXT NOT NULL,
                seen_at INTEGER NOT NULL
            );
        """)
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(candidates)")}
        if "external_views" not in columns:
            self.connection.execute(
                "ALTER TABLE candidates ADD COLUMN external_views INTEGER NOT NULL DEFAULT 0"
            )
        if "external_likes" not in columns:
            self.connection.execute(
                "ALTER TABLE candidates ADD COLUMN external_likes INTEGER NOT NULL DEFAULT 0"
            )
        self.connection.executemany(
            "DELETE FROM candidates WHERE uri = ?",
            ((uri,) for uri in (*WALLPAPER_SOURCES.values(), *LEGACY_CATALOG_PAGES)),
        )
        self.connection.executemany(
            "DELETE FROM candidates WHERE uri = ? AND score <= 0.1 AND views = 0",
            ((uri,) for uri in LEGACY_YOUTUBE_FEATURED),
        )
        self.connection.executemany(
            """INSERT OR IGNORE INTO candidates
               (uri,title,source,tags,score,views,last_seen)
               VALUES(?,?,?,?,0.1,0,0)""",
            DEFAULT_SUGGESTIONS,
        )
        self.connection.execute(
            "UPDATE candidates SET score=MAX(score,0.5) WHERE source='steamcommunity.com'"
        )
        self.connection.executemany(
            """INSERT INTO candidates
               (uri,title,source,tags,score,views,last_seen,external_views,external_likes)
               VALUES(?,?,?,?,0.1,0,0,?,?)
               ON CONFLICT(uri) DO UPDATE SET title=excluded.title, source=excluded.source,
               tags=excluded.tags, external_views=excluded.external_views,
               external_likes=excluded.external_likes""",
            YOUTUBE_FEATURED,
        )
        legacy_impressions = self.connection.execute(
            """SELECT impressions.uri, COALESCE(candidates.title, '')
               FROM suggestion_impressions AS impressions
               LEFT JOIN candidates ON candidates.uri = impressions.uri
               GROUP BY impressions.uri"""
        ).fetchall()
        self.connection.executemany(
            """INSERT OR IGNORE INTO suggestion_seen(fingerprint,uri,seen_at)
               VALUES(?,?,?)""",
            ((content_fingerprint(uri, title), uri, int(time.time()))
             for uri, title in legacy_impressions),
        )
        self.connection.commit()

    def record(self, uri, title, weight, candidate=None):
        if not uri or not title or not uri.startswith(("http://", "https://")):
            return
        if candidate is None:
            lowered = title.casefold()
            candidate = "wallpaper" in lowered and "wallpapers" not in lowered
        if not candidate:
            self.reinforce(title, weight * 0.3)
            return
        source = urlparse(uri).netloc.removeprefix("www.") or "web"
        tags = content_tags(title, uri)
        now = int(time.time())
        self.connection.execute(
            """INSERT INTO candidates(uri,title,source,tags,score,views,last_seen)
               VALUES(?,?,?,?,?,1,?)
               ON CONFLICT(uri) DO UPDATE SET title=excluded.title, tags=excluded.tags,
               score=candidates.score+excluded.score, views=candidates.views+1,
               last_seen=excluded.last_seen""",
            (uri, title[:240], source, " ".join(tags), weight, now),
        )
        for tag in tags:
            self.connection.execute(
                """INSERT INTO tag_profile(tag,weight) VALUES(?,?)
                   ON CONFLICT(tag) DO UPDATE SET weight=tag_profile.weight+excluded.weight""",
                (tag, weight),
            )
        self.connection.commit()

    def add_candidates(self, candidates):
        known = {
            content_fingerprint(uri, title)
            for uri, title in self.connection.execute("SELECT uri,title FROM candidates")
        }
        unique = []
        for candidate in candidates:
            fingerprint = content_fingerprint(candidate[0], candidate[1])
            if fingerprint in known:
                continue
            known.add(fingerprint)
            unique.append(candidate)
        before = self.connection.total_changes
        self.connection.executemany(
            """INSERT OR IGNORE INTO candidates
               (uri,title,source,tags,score,views,last_seen)
               VALUES(?,?,?,?,0.1,0,0)""",
            unique,
        )
        self.connection.commit()
        return self.connection.total_changes - before

    def candidate_count(self):
        return len({
            content_fingerprint(uri, title)
            for uri, title in self.connection.execute("SELECT uri,title FROM candidates")
        })

    def reinforce(self, title, weight):
        for tag in content_tags(title):
            self.connection.execute(
                """INSERT INTO tag_profile(tag,weight) VALUES(?,?)
                   ON CONFLICT(tag) DO UPDATE SET weight=tag_profile.weight+excluded.weight""",
                (tag, weight),
            )
        self.connection.commit()

    def seen_fingerprints(self):
        return {row[0] for row in self.connection.execute(
            "SELECT fingerprint FROM suggestion_seen"
        )}

    def record_impressions(self, recommendations):
        now = int(time.time())
        self.connection.executemany(
            """INSERT OR IGNORE INTO suggestion_seen(fingerprint,uri,seen_at)
               VALUES(?,?,?)""",
            ((content_fingerprint(item[1], item[2]), item[1], now)
             for item in recommendations),
        )
        self.connection.commit()

    def recommendations(self, limit=12, exclude_fingerprints=(), seed_uri=None):
        profile = dict(self.connection.execute("SELECT tag,weight FROM tag_profile"))
        rows = self.connection.execute(
            """SELECT uri,title,source,tags,score,views,last_seen,
                      external_views,external_likes FROM candidates"""
        ).fetchall()
        scored = []
        for uri, title, source, tags_text, score, views, last_seen, external_views, external_likes in rows:
            tags = tags_text.split()
            affinity = sum(profile.get(tag, 0.0) for tag in tags)
            freshness = min(1.0, max(0.0, (time.time() - last_seen) / 604800))
            reach = min(1.0, math.log10(external_views + 1) / 6.0) if external_views else 0.0
            like_rate = external_likes / external_views if external_views else 0.0
            engagement = min(1.0, like_rate / 0.08)
            popularity = reach * 0.6 + engagement * 0.4
            total = (score * 0.5 + affinity * 0.3 + freshness * 0.2
                     + popularity * 0.5 - views * 0.05)
            scored.append((total, uri, title, source, tags, score, views, popularity,
                           external_views, external_likes))
        deduplicated = {}
        for item in scored:
            fingerprint = content_fingerprint(item[1], item[2])
            previous = deduplicated.get(fingerprint)
            if previous is None or item[0] > previous[0]:
                deduplicated[fingerprint] = item
        scored = list(deduplicated.values())
        if scored:
            minimum = min(item[0] for item in scored)
            maximum = max(item[0] for item in scored)
            span = maximum - minimum
            calibrated = []
            for (total, uri, title, source, tags, interaction_score, views, popularity,
                 external_views, external_likes) in scored:
                relative = 0.5 if span < 0.0001 else (total - minimum) / span
                evidence = max(0.0, interaction_score - 0.1) + views * 0.5
                confidence = min(1.0, evidence / 12.0)
                if external_views:
                    rating = 3.0 + popularity * 2.0
                    confidence = min(1.0, math.log10(external_views + 1) / 5.0)
                else:
                    raw_rating = 3.0 + relative * 2.0
                    rating = 3.0 + (raw_rating - 3.0) * confidence
                calibrated.append((total, uri, title, source, tags, rating, confidence,
                                   external_views, external_likes))
            scored = calibrated
        blocked = set(exclude_fingerprints).union(self.seen_fingerprints())
        unseen = [item for item in scored
                  if content_fingerprint(item[1], item[2]) not in blocked]
        seed_tags = next((set(item[4]) for item in scored if item[1] == seed_uri), set())
        known_tags = {tag for tag, weight in profile.items() if weight > 0}
        return randomized_suggestions(
            unseen, limit, (), seed_tags, known_tags, EXPLORATION_RATE
        )


def randomized_suggestions(primary, limit, fallback=(), seed_tags=(), known_tags=(),
                           exploration_rate=0.0):
    """Tirage pondéré sans répétition, avec réutilisation en dernier recours."""
    generator = random.SystemRandom()
    result = []
    seed_tags = set(seed_tags)
    known_tags = set(known_tags)
    primary = list(primary)
    exploration = [item for item in primary if not known_tags.intersection(item[4])]
    exploration_count = min(len(exploration), max(0, math.ceil(limit * exploration_rate)))
    if exploration_count:
        discovered = generator.sample(exploration, exploration_count)
        result.extend(discovered)
        primary = [item for item in primary if item not in discovered]
    for pool in (primary, list(fallback)):
        while pool and len(result) < limit:
            floor = min(item[0] for item in pool)
            weights = [
                max(0.05, item[0] - floor + 0.15)
                * (5 ** len(seed_tags.intersection(item[4])))
                for item in pool
            ]
            selected = generator.choices(pool, weights=weights, k=1)[0]
            result.append(selected)
            pool.remove(selected)
    generator.shuffle(result)
    return result


def load_suggestion_history():
    try:
        history = json.loads(SUGGESTION_HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(history, list):
        return []
    return [uri for uri in history if isinstance(uri, str)][-SUGGESTION_COOLDOWN:]


def save_suggestion_history(previous, current):
    history = []
    for uri in (*previous, *current):
        if uri in history:
            history.remove(uri)
        history.append(uri)
    history = history[-SUGGESTION_COOLDOWN:]
    try:
        RUNTIME_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        RUNTIME_DIR.chmod(0o700)
        atomic_write_text(SUGGESTION_HISTORY_FILE, json.dumps(history) + "\n")
    except OSError:
        pass


class DownloadLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href", "")
        lowered = href.lower()
        if "/dl/" in lowered or lowered.endswith(tuple(VIDEO_EXTENSIONS)):
            self.links.append(href)


class PreviewParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.preview = ""

    def handle_starttag(self, tag, attrs):
        if tag != "meta" or self.preview:
            return
        values = dict(attrs)
        if values.get("property") in ("og:image", "twitter:image"):
            self.preview = values.get("content", "")


class SourceSuggestionParser(HTMLParser):
    def __init__(self, base_uri):
        super().__init__()
        self.base_uri = base_uri
        self.candidates = []
        self.frontier = []
        self.pending_candidate = None
        self.pending_text = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag != "a":
            if self.pending_candidate is not None and values.get("alt"):
                self.pending_text.append(values["alt"].strip())
            return
        self.finish_pending_candidate()
        href = urljoin(self.base_uri, values.get("href", ""))
        parsed = urlparse(href)
        if not source_uri_is_safe(href):
            return
        href = parsed._replace(fragment="").geturl()
        parsed = urlparse(href)
        path = parsed.path.casefold()
        query = parse_qs(parsed.query, keep_blank_values=True)
        host = source_uri_host(href)
        base_host = source_uri_host(self.base_uri)
        same_host = bool(host and host == base_host)
        base_path = urlparse(self.base_uri).path.casefold()
        base_query = parse_qs(urlparse(self.base_uri).query, keep_blank_values=True)
        is_pagination = same_host and is_next_source_page(
            host, base_path, base_query, path, query
        )
        if is_pagination and href.rstrip("/") != self.base_uri.rstrip("/"):
            self.frontier.append(href)
        is_candidate = same_host and is_source_candidate(host, path, query)
        if not is_candidate or href.rstrip("/") == self.base_uri.rstrip("/"):
            return
        explicit_title = values.get("title") or values.get("aria-label")
        title = explicit_title
        if not title:
            slug = Path(path.rstrip("/")).name.replace("-", " ").replace("_", " ")
            title = slug or "Fond d'écran animé"
        self.candidates.append((href, title[:240]))
        if not explicit_title:
            self.pending_candidate = len(self.candidates) - 1

    def handle_data(self, data):
        if self.pending_candidate is not None and data.strip():
            self.pending_text.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "a":
            self.finish_pending_candidate()

    def close(self):
        self.finish_pending_candidate()
        super().close()

    def finish_pending_candidate(self):
        if self.pending_candidate is None:
            return
        text = re.sub(r"\s+", " ", " ".join(self.pending_text)).strip()
        if text:
            uri, _fallback = self.candidates[self.pending_candidate]
            self.candidates[self.pending_candidate] = (uri, text[:240])
        self.pending_candidate = None
        self.pending_text = []


def source_uri_host(uri):
    try:
        parsed = urlparse(uri)
        port = parsed.port
    except ValueError:
        return ""
    if (parsed.scheme.casefold() != "https" or parsed.username or parsed.password
            or port not in {None, 443}):
        return ""
    return (parsed.hostname or "").casefold().removeprefix("www.")


def source_uri_is_safe(uri):
    return bool(source_uri_host(uri))


def single_query_value(query, key, pattern):
    values = query.get(key, [])
    return len(values) == 1 and bool(re.fullmatch(pattern, values[0]))


def source_page_number(host, path, query):
    if host == "steamcommunity.com" and re.fullmatch(r"/workshop/browse/?", path):
        if query.get("appid") != ["431960"]:
            return None
        if "p" not in query:
            return 1
        return int(query["p"][0]) if single_query_value(query, "p", r"[1-9]\d*") else None
    patterns = {
        "motionbgs.com": r"/page/([1-9]\d*)/?",
        "moewalls.com": r"/page/([1-9]\d*)/?",
        "vsthemes.org": r"/en/wallpapers/page/([1-9]\d*)/?",
    }
    roots = {
        "motionbgs.com": "/",
        "moewalls.com": "/",
        "vsthemes.org": "/en/wallpapers/",
    }
    if host in roots and path.rstrip("/") == roots[host].rstrip("/") and not query:
        return 1
    match = re.fullmatch(patterns.get(host, r"(?!x)x"), path)
    return int(match.group(1)) if match and not query else None


def is_next_source_page(host, base_path, base_query, path, query):
    current = source_page_number(host, base_path, base_query)
    following = source_page_number(host, path, query)
    return current is not None and following == current + 1


def is_source_candidate(host, path, query):
    if host == "steamcommunity.com":
        return (bool(re.fullmatch(r"/sharedfiles/filedetails/?", path))
                and single_query_value(query, "id", r"[1-9]\d*"))
    if host in {"youtube.com", "m.youtube.com"}:
        return (bool(re.fullmatch(r"/watch/?", path))
                and single_query_value(query, "v", r"[A-Za-z0-9_-]{11}"))
    if host == "motionbgs.com":
        blocked = {"privacy-policy", "terms-of-use", "contact-us", "about-us"}
        slug = path.strip("/")
        return (slug not in blocked
                and bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", slug)))
    if host == "moewalls.com":
        return bool(re.fullmatch(r"/[^/]+/[^/]+-live-wallpaper/?", path))
    if host == "vsthemes.org":
        return bool(re.fullmatch(
            r"/en/wallpapers/(?!page(?:/|$))(?:[^/]+/)*[^/]+\.html", path
        ))
    return False


def fetch_youtube_channel_candidates(source_uri):
    parsed = urlparse(source_uri)
    host = source_uri_host(source_uri)
    if host not in {"youtube.com", "m.youtube.com"} or parsed.path == "/watch":
        return None
    command = [
        str(LOCAL_YTDLP) if LOCAL_YTDLP.is_file() else "yt-dlp",
        "--flat-playlist", "--dump-json", "--skip-download", "--ignore-errors",
        source_uri,
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=180, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    candidates = []
    for line in result.stdout.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        video_id = str(item.get("id") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            continue
        uri = f"https://www.youtube.com/watch?v={video_id}"
        title = item.get("title") or "Vidéo YouTube"
        candidates.append((
            uri, str(title)[:240], "youtube.com",
            " ".join(content_tags(str(title), uri)),
        ))
    return candidates


def fetch_source_candidates(source_uri):
    youtube_candidates = fetch_youtube_channel_candidates(source_uri)
    if youtube_candidates:
        return youtube_candidates, []
    try:
        request = Request(source_uri, headers={"User-Agent": "Mozilla/5.0 MPVpaperEngine/1.0"})
        with urlopen(request, timeout=12) as response:
            if source_uri_host(response.geturl()) != source_uri_host(source_uri):
                return None
            parser = SourceSuggestionParser(source_uri)
            parser.feed(response.read().decode("utf-8", "replace"))
            parser.close()
    except (OSError, ValueError):
        return None
    unique = {}
    for uri, title in parser.candidates:
        unique.setdefault(uri.split("#", 1)[0], title)
    candidates = [
        (uri, title, urlparse(uri).netloc.removeprefix("www.") or "web",
         " ".join(content_tags(title, uri)))
        for uri, title in unique.items()
    ]
    return candidates, list(dict.fromkeys(parser.frontier))


def load_source_frontier():
    try:
        data = json.loads(SOURCE_FRONTIER_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if data.get("version") != SOURCE_FRONTIER_VERSION:
        return [], set()
    queue = [uri for uri in data.get("queue", [])
             if isinstance(uri, str) and source_uri_is_safe(uri)]
    visited = {uri for uri in data.get("visited", [])
               if isinstance(uri, str) and source_uri_is_safe(uri)}
    return queue, visited


def save_source_frontier(queue, visited):
    CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    CONFIG_DIR.chmod(0o700)
    atomic_write_text(SOURCE_FRONTIER_FILE, json.dumps({
        "version": SOURCE_FRONTIER_VERSION,
        "queue": queue,
        "visited": sorted(visited),
    }) + "\n")


def source_host_allowed(uri, allowed_hosts):
    host = source_uri_host(uri)
    return bool(host and host in allowed_hosts)


def prefetch_suggestions(desired_new=None, page_budget=None):
    """Étend la réserve sans plafond global.

    ``desired_new`` et ``page_budget`` découpent uniquement le travail d'une passe ;
    la frontière persistante permet à toutes les passes suivantes de continuer.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with SOURCE_FRONTIER_LOCK.open("a+", encoding="utf-8") as lock_stream:
        fcntl.flock(lock_stream, fcntl.LOCK_EX)
        store = TasteStore()
        initial_count = store.candidate_count()
        queue, visited = load_source_frontier()
        roots = list(WALLPAPER_SOURCES.values())
        if not queue:
            queue = [uri for uri in roots if uri not in visited]
        if not queue:
            visited.clear()
            queue = list(roots)
        allowed_hosts = {source_uri_host(uri) for uri in roots}
        pages_read = 0
        added = 0
        failed_this_pass = set()
        while queue:
            if page_budget is not None and pages_read >= page_budget:
                break
            if desired_new is not None and added >= desired_new:
                break
            source_uri = queue.pop(0)
            if source_uri in visited:
                continue
            if source_uri in failed_this_pass:
                queue.append(source_uri)
                if all(uri in failed_this_pass or uri in visited for uri in queue):
                    break
                continue
            pages_read += 1
            fetched = fetch_source_candidates(source_uri)
            if fetched is None:
                failed_this_pass.add(source_uri)
                queue.append(source_uri)
                save_source_frontier(queue, visited)
                continue
            visited.add(source_uri)
            candidates, discovered_pages = fetched
            candidates = [candidate for candidate in candidates
                          if source_host_allowed(candidate[0], allowed_hosts)]
            added += store.add_candidates(candidates)
            discovered = [*discovered_pages]
            for uri in discovered:
                if (source_host_allowed(uri, allowed_hosts)
                        and uri not in visited and uri not in queue):
                    queue.append(uri)
            save_source_frontier(queue, visited)
        save_source_frontier(queue, visited)
        count = store.candidate_count()
        store.connection.close()
        fcntl.flock(lock_stream, fcntl.LOCK_UN)
    print(f"Préchargement continu : {count} fiches distinctes "
          f"({count - initial_count:+d}, {pages_read} pages explorées)")
    if desired_new is None:
        return 0
    return 0 if count - initial_count >= desired_new else 3


def page_download_url(uri):
    try:
        request = Request(uri, headers={"User-Agent": "Mozilla/5.0 MPVpaperEngine/1.0"})
        with urlopen(request, timeout=15) as response:
            parser = DownloadLinkParser()
            parser.feed(response.read().decode("utf-8", "replace"))
        if parser.links:
            ranked = sorted(
                parser.links,
                key=lambda link: ("/4k/" in link.lower(), "/hd/" in link.lower()),
                reverse=True,
            )
            return urljoin(uri, ranked[0])
    except (OSError, ValueError):
        pass
    return uri


def suggestion_thumbnail_path(uri):
    return SUGGESTION_CACHE / f"{hashlib.sha256(uri.encode()).hexdigest()}.preview"


def compact_count(value):
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} M".replace(".0", "").replace(".", ",")
    if value >= 1_000:
        return f"{value / 1_000:.1f} k".replace(".0", "").replace(".", ",")
    return str(value)


def fetch_suggestion_thumbnail(uri, destination):
    try:
        request = Request(uri, headers={"User-Agent": "Mozilla/5.0 MPVpaperEngine/1.0"})
        with urlopen(request, timeout=15) as response:
            parser = PreviewParser()
            parser.feed(response.read().decode("utf-8", "replace"))
        if not parser.preview:
            return False
        image_request = Request(urljoin(uri, parser.preview), headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(image_request, timeout=15) as response:
            destination.write_bytes(response.read())
        return True
    except (OSError, ValueError):
        return False


def bounded_config_number(value, default, minimum, maximum, number_type=int):
    try:
        parsed = number_type(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(minimum, min(maximum, parsed))


def normalize_config_profile(data, output="*"):
    source = data if isinstance(data, dict) else {}
    profile = dict(DEFAULT_CONFIG)
    wallpaper = source.get("wallpaper", "")
    profile["wallpaper"] = wallpaper if isinstance(wallpaper, str) else ""
    requested_output = source.get("output", output)
    profile["output"] = requested_output if isinstance(requested_output, str) and 0 < len(requested_output) <= 128 else output
    profile["volume"] = bounded_config_number(source.get("volume"), 0, 0, 100)
    profile["speed"] = bounded_config_number(source.get("speed"), 1.0, 0.1, 5.0, float)
    for key in ("loop", "hardware_decode", "auto_pause", "autostart"):
        if isinstance(source.get(key), bool):
            profile[key] = source[key]
    for key in ("brightness", "contrast", "gamma", "saturation", "hue",
                "red_balance", "green_balance", "blue_balance"):
        profile[key] = bounded_config_number(source.get(key), COLOR_DEFAULTS[key], -100, 100)
    profile["temperature"] = bounded_config_number(source.get("temperature"), 6500, 1000, 40000)
    return profile


def load_config():
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    config = normalize_config_profile(data)
    assignments = data.get("assignments") if isinstance(data, dict) else None
    config["assignments"] = {}
    if isinstance(assignments, dict):
        for output, assignment in assignments.items():
            if not isinstance(output, str) or not 0 < len(output) <= 128 or not isinstance(assignment, dict):
                continue
            profile = normalize_config_profile(assignment, output=output)
            config["assignments"][output] = {
                key: profile[key] for key in DEFAULT_CONFIG if key != "output"
            }
    elif config["wallpaper"]:
        config["assignments"][config["output"]] = {
            key: config[key] for key in DEFAULT_CONFIG if key != "output"
        }
    return config


def save_config(config):
    CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    CONFIG_DIR.chmod(0o700)
    atomic_write_text(CONFIG_FILE, json.dumps(config, indent=2) + "\n")


def bounded_process(command, timeout, **options):
    try:
        return subprocess.run(command, timeout=timeout, check=False, **options)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            command, 124, stdout="",
            stderr=f"Opération interrompue après {timeout} secondes.",
        )
    except OSError as error:
        return subprocess.CompletedProcess(command, 127, stdout="", stderr=str(error))


def monitor_names():
    try:
        result = subprocess.run(
            ["hyprctl", "monitors", "all", "-j"], capture_output=True,
            text=True, timeout=3, check=False,
        )
        return [item["name"] for item in json.loads(result.stdout)]
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, KeyError):
        return []


def probe_video_duration(path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=4, check=False,
        )
        seconds = int(float(result.stdout.strip()))
        return f"{seconds // 60}:{seconds % 60:02d}"
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return "vidéo"


def thumbnail_path(video):
    signature = f"{video.resolve()}:{video.stat().st_mtime_ns}"
    return CACHE_DIR / f"{hashlib.sha256(signature.encode()).hexdigest()}.jpg"


def metadata_key(video):
    signature = f"{video.resolve()}:{video.stat().st_mtime_ns}"
    return hashlib.sha256(signature.encode()).hexdigest()


class WallpaperCard(Gtk.FlowBoxChild):
    def __init__(self, path, thumbnail, duration):
        super().__init__()
        self.path = path
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                          css_classes=["wallpaper-card"])
        picture = Gtk.Picture.new_for_filename(str(thumbnail)) if thumbnail.exists() else Gtk.Picture()
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.set_size_request(220, 124)
        content.append(picture)
        name = Gtk.Label(label=path.stem, xalign=0, ellipsize=3, max_width_chars=25)
        name.add_css_class("card-title")
        content.append(name)
        content.append(Gtk.Label(label=duration, xalign=0, css_classes=["secondary-text"]))
        self.set_child(content)


class SuggestionCard(Gtk.FlowBoxChild):
    def __init__(self, title, source, tags, rating, confidence, thumbnail,
                 external_views, external_likes, open_callback, favorite_callback):
        super().__init__()
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                          css_classes=["suggestion-card"])
        self.picture = (Gtk.Picture.new_for_filename(str(thumbnail))
                        if thumbnail.exists() else Gtk.Picture())
        self.picture.set_content_fit(Gtk.ContentFit.COVER)
        self.picture.set_size_request(250, 150)
        content.append(self.picture)
        content.append(Gtk.Label(label=title, xalign=0, wrap=True, lines=2,
                                 ellipsize=3, css_classes=["card-title"]))
        content.append(Gtk.Label(label=source, xalign=0, ellipsize=3,
                                 css_classes=["suggestion-source"]))
        if external_views:
            content.append(Gtk.Label(
                label=(f"{compact_count(external_views)} vues · "
                       f"{compact_count(external_likes)} J’aime"),
                xalign=0, css_classes=["secondary-text"],
            ))
        details = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        stars = max(1, min(5, int(round(rating))))
        tooltip = f"Note calculée sur les interactions · confiance {confidence * 100:.0f} %"
        if external_views:
            tooltip = ("Note publique : 60 % portée des vues et 40 % taux de J’aime · "
                       f"confiance {confidence * 100:.0f} %")
        rating_label = Gtk.Label(
            label="★" * stars + "☆" * (5 - stars) + f"  {rating:.1f}",
            xalign=0, hexpand=True, css_classes=["suggestion-rating"],
            tooltip_text=tooltip,
        )
        details.append(rating_label)
        favorite = Gtk.Button(icon_name="emblem-favorite-symbolic", tooltip_text="J’aime")
        favorite.connect("clicked", favorite_callback)
        details.append(favorite)
        content.append(details)
        content.append(Gtk.Label(label=" · ".join(tags[:3]), xalign=0, ellipsize=3,
                                 css_classes=["secondary-text"]))
        open_button = Gtk.Button(label="Ouvrir", css_classes=["suggested-action"])
        open_button.connect("clicked", open_callback)
        content.append(open_button)
        self.set_child(content)


class MPVpaperWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="MPVpaper Engine")
        self.set_default_size(1120, 720)
        self.set_size_request(760, 520)
        self.config = load_config()
        self.metadata = self.load_metadata()
        self.taste = TasteStore()
        self.suggestion_thumbnail_attempted = set()
        self.displayed_suggestion_uris = load_suggestion_history()
        self.suggestion_feed_uris = []
        self.suggestion_feed_fingerprints = set()
        self.suggestion_cards = {}
        self.suggestion_seed_uri = None
        self.suggestion_loading = False
        self.suggestion_seed_update_id = None
        self.source_refreshing = False
        self.last_source_refresh = 0.0
        self.source_retry_id = None
        self.source_retry_delay = SOURCE_REFRESH_INTERVAL
        self.source_refresh_wanted = 1
        self.selected = Path(self.config["wallpaper"]) if self.config["wallpaper"] else None
        self.color_controls = {}
        self.color_labels = {}
        self.color_loading = False
        self.color_update_id = None
        self.cards = []
        LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        SUGGESTION_CACHE.mkdir(parents=True, exist_ok=True)
        self.build_ui()
        self.load_library()
        self.refresh_status()

    def build_ui(self):
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        import_button = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Importer des vidéos")
        import_button.connect("clicked", self.import_videos)
        header.pack_start(import_button)
        youtube_button = Gtk.Button(icon_name="video-x-generic-symbolic",
                                    tooltip_text="Importer une vidéo YouTube")
        youtube_button.connect("clicked", self.import_youtube)
        header.pack_start(youtube_button)
        refresh_button = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Actualiser la bibliothèque")
        refresh_button.connect("clicked", lambda _button: self.load_library())
        header.pack_start(refresh_button)
        stop_button = Gtk.Button(icon_name="media-playback-stop-symbolic", tooltip_text="Arrêter le fond vidéo")
        stop_button.connect("clicked", self.stop_wallpaper)
        header.pack_end(stop_button)
        toolbar.add_top_bar(header)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, wide_handle=True)
        paned.set_position(760)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)

        library = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=16,
                          margin_bottom=16, margin_start=18, margin_end=18)
        self.search = Gtk.SearchEntry(placeholder_text="Rechercher dans la bibliothèque")
        self.search.connect("search-changed", self.filter_library)
        library.append(self.search)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.SINGLE, homogeneous=False,
                                column_spacing=12, row_spacing=12, min_children_per_line=2,
                                max_children_per_line=3)
        self.flow.set_valign(Gtk.Align.START)
        self.flow.connect("selected-children-changed", self.selection_changed)
        scroll.set_child(self.flow)
        library.append(scroll)
        paned.set_start_child(library)

        inspector_scroll = Gtk.ScrolledWindow(width_request=320)
        inspector = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                            margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        inspector.append(Gtk.Label(label="Réglages", xalign=0, css_classes=["title-2"]))
        self.selected_label = Gtk.Label(label="Sélectionnez une vidéo", xalign=0, wrap=True,
                                        css_classes=["dim-label"])
        inspector.append(self.selected_label)

        output_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        output_box.append(Gtk.Label(label="Écran", xalign=0, css_classes=["heading"]))
        outputs = ["Tous les écrans (*)", *monitor_names()]
        self.output_names = ["*", *outputs[1:]]
        self.output = Gtk.DropDown.new_from_strings(outputs)
        current_output = self.config["output"]
        self.output.set_selected(self.output_names.index(current_output) if current_output in self.output_names else 0)
        self.output.connect("notify::selected", self.output_changed)
        output_box.append(self.output)
        inspector.append(output_box)

        volume_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.volume_label = Gtk.Label(label=f"Volume : {self.config['volume']} %", xalign=0,
                                      css_classes=["heading"])
        self.volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        self.volume.set_value(self.config["volume"])
        self.volume.connect("value-changed", lambda scale: self.volume_label.set_text(f"Volume : {int(scale.get_value())} %"))
        volume_box.append(self.volume_label)
        volume_box.append(self.volume)
        inspector.append(volume_box)

        speed_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        speed_box.append(Gtk.Label(label="Vitesse", xalign=0, css_classes=["heading"]))
        self.speeds = [0.5, 0.75, 1.0, 1.25, 1.5]
        self.speed = Gtk.DropDown.new_from_strings([f"{value:g}×" for value in self.speeds])
        self.speed.set_selected(self.speeds.index(float(self.config["speed"])) if float(self.config["speed"]) in self.speeds else 2)
        speed_box.append(self.speed)
        inspector.append(speed_box)

        self.loop = self.switch_row("Lecture en boucle", "Recommencer la vidéo automatiquement", self.config["loop"])
        self.hardware = self.switch_row("Décodage matériel", "Réduit l’utilisation du processeur", self.config["hardware_decode"])
        self.auto_pause = self.switch_row("Pause en plein écran", "Économise les ressources pendant les jeux", self.config["auto_pause"])
        self.autostart = self.switch_row("Restaurer à la connexion", "Relance le dernier fond sélectionné", self.config["autostart"])
        for row in (self.loop[0], self.hardware[0], self.auto_pause[0], self.autostart[0]):
            inspector.append(row)

        self.apply_button = Gtk.Button(label="Appliquer le fond", css_classes=["suggested-action", "pill"])
        self.apply_button.set_sensitive(self.selected is not None)
        self.apply_button.connect("clicked", self.apply_wallpaper)
        inspector.append(self.apply_button)
        self.login_button = Gtk.Button(label="Utiliser pour l’écran de connexion")
        self.login_button.set_sensitive(self.selected is not None)
        self.login_button.connect("clicked", self.set_login_wallpaper)
        inspector.append(self.login_button)
        self.status = Gtk.Label(label="", xalign=0, wrap=True, css_classes=["dim-label"])
        inspector.append(self.status)
        inspector_scroll.set_child(inspector)
        paned.set_end_child(inspector_scroll)

        self.views = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.views.add_titled(paned, "library", "Bibliothèque")
        self.views.add_titled(self.build_discover_view(), "discover", "Découvrir")
        self.views.add_titled(self.build_suggestions_view(), "suggestions", "Suggestions")
        self.views.add_titled(self.build_themes_view(), "themes", "Thèmes")
        self.views.add_titled(self.build_colors_view(), "colors", "Couleurs")
        self.views.connect("notify::visible-child-name", self.view_changed)
        switcher = Gtk.StackSwitcher(stack=self.views)
        header.set_title_widget(switcher)
        toolbar.set_content(self.views)
        self.set_content(toolbar)

    def build_colors_view(self):
        page = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=18,
            margin_top=20, margin_bottom=24, margin_start=24, margin_end=24,
        )
        page.append(Gtk.Label(
            label="Couleurs du fond vidéo", xalign=0, css_classes=["title-1"],
        ))
        page.append(Gtk.Label(
            label="Ajustements appliqués en direct par MPVpaper Engine à l’écran sélectionné.",
            xalign=0, wrap=True, css_classes=["dim-label"],
        ))

        output_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        output_row.append(Gtk.Label(label="Écran", xalign=0, hexpand=True,
                                    css_classes=["heading"]))
        self.color_output_names = list(self.output_names)
        output_labels = ["Tous les écrans (*)" if name == "*" else name
                         for name in self.color_output_names]
        self.color_output = Gtk.DropDown.new_from_strings(output_labels)
        self.color_output.set_selected(self.output.get_selected())
        self.color_output.connect("notify::selected", self.color_output_changed)
        output_row.append(self.color_output)
        page.append(output_row)

        page.append(Gtk.Label(label="Profils rapides", xalign=0, css_classes=["title-2"]))
        presets = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                              column_spacing=8, row_spacing=8,
                              min_children_per_line=2, max_children_per_line=5)
        for name in COLOR_PRESETS:
            button = Gtk.Button(label=name)
            button.connect("clicked", self.apply_color_preset, name)
            presets.append(button)
        page.append(presets)

        page.append(Gtk.Label(label="Ajustements", xalign=0, css_classes=["title-2"]))
        grid = Gtk.Grid(column_spacing=12, row_spacing=12,
                        column_homogeneous=True)
        controls = (
            ("brightness", "Luminosité", -100, 100, 1, "%"),
            ("contrast", "Contraste", -100, 100, 1, "%"),
            ("gamma", "Gamma", -100, 100, 1, ""),
            ("saturation", "Saturation", -100, 100, 1, "%"),
            ("hue", "Teinte", -100, 100, 1, "°"),
            ("temperature", "Température", 1000, 10000, 100, " K"),
            ("red_balance", "Rouge", -100, 100, 1, "%"),
            ("green_balance", "Vert", -100, 100, 1, "%"),
            ("blue_balance", "Bleu", -100, 100, 1, "%"),
        )
        for index, spec in enumerate(controls):
            grid.attach(self.color_control(*spec), index % 3, index // 3, 1, 1)
        page.append(grid)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
                          halign=Gtk.Align.END)
        reset = Gtk.Button(label="Réinitialiser", icon_name="view-refresh-symbolic")
        reset.connect("clicked", self.apply_color_preset, "Original")
        actions.append(reset)
        cancel = Gtk.Button(label="Annuler")
        cancel.connect("clicked", self.cancel_color_preview)
        actions.append(cancel)
        apply_button = Gtk.Button(label="Appliquer", css_classes=["suggested-action"])
        apply_button.connect("clicked", self.apply_colors_now)
        actions.append(apply_button)
        page.append(actions)
        self.color_status = Gtk.Label(label="", xalign=0, wrap=True,
                                      css_classes=["dim-label"])
        page.append(self.color_status)
        self.load_color_controls()

        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(page)
        return scroll

    def color_control(self, key, title, minimum, maximum, step, suffix):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                       margin_top=10, margin_bottom=10,
                       margin_start=12, margin_end=12,
                       css_classes=["card"])
        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        heading.append(Gtk.Label(label=title, xalign=0, hexpand=True,
                                 css_classes=["heading"]))
        value_label = Gtk.Label(label="", css_classes=["dim-label"])
        self.color_labels[key] = (value_label, suffix)
        heading.append(value_label)
        card.append(heading)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,
                                         minimum, maximum, step)
        scale.set_hexpand(True)
        scale.set_draw_value(False)
        scale.connect("value-changed", self.color_value_changed, key)
        self.color_controls[key] = scale
        card.append(scale)
        return card

    def selected_color_output(self):
        return self.color_output_names[self.color_output.get_selected()]

    def color_profile(self):
        output = self.selected_color_output()
        return {
            **COLOR_DEFAULTS,
            **self.config.get("assignments", {}).get(output, {}),
        }

    def load_color_controls(self):
        if not self.color_controls:
            return
        self.color_loading = True
        profile = self.color_profile()
        for key, control in self.color_controls.items():
            control.set_value(profile.get(key, COLOR_DEFAULTS[key]))
            self.update_color_label(key)
        self.color_loading = False

    def update_color_label(self, key):
        label, suffix = self.color_labels[key]
        value = int(self.color_controls[key].get_value())
        label.set_text(f"{value:+d}{suffix}" if value and key != "temperature"
                       else f"{value}{suffix}")

    def color_output_changed(self, _dropdown, _property):
        self.load_color_controls()
        self.color_status.set_text("")

    def color_value_changed(self, _scale, key):
        self.update_color_label(key)
        if self.color_loading:
            return
        if self.color_update_id is not None:
            GLib.source_remove(self.color_update_id)
        self.color_update_id = GLib.timeout_add(120, self.preview_colors)

    def current_colors(self):
        return {key: int(control.get_value())
                for key, control in self.color_controls.items()}

    def preview_colors(self):
        self.color_update_id = None
        output = self.selected_color_output()
        self.color_status.set_text("Aperçu en temps réel…")
        self.run_color_controller(output, preview=self.current_colors())
        return False

    def run_color_controller(self, output, preview=None):
        def worker():
            command = [str(CONTROLLER), "apply-colors", "--output", output]
            if preview is not None:
                command = [
                    str(CONTROLLER), "preview-colors", "--output", output,
                    "--settings", json.dumps(preview),
                ]
            result = bounded_process(
                command,
                timeout=20, capture_output=True, text=True,
            )
            GLib.idle_add(self.colors_finished, result)
        threading.Thread(target=worker, daemon=True).start()

    def colors_finished(self, result):
        if result.returncode == 0:
            self.color_status.set_text("Couleurs appliquées en direct au fond vidéo.")
        else:
            message = result.stderr.strip() or "Lancez d’abord un fond vidéo sur cet écran."
            self.color_status.set_text(message)
        return False

    def apply_color_preset(self, _button, name):
        self.color_loading = True
        for key, value in COLOR_PRESETS[name].items():
            self.color_controls[key].set_value(value)
            self.update_color_label(key)
        self.color_loading = False
        self.preview_colors()

    def apply_colors_now(self, _button):
        output = self.selected_color_output()
        assignments = self.config.setdefault("assignments", {})
        profile = {**DEFAULT_CONFIG, **assignments.get(output, {})}
        profile.update(self.current_colors())
        assignments[output] = {key: value for key, value in profile.items()
                               if key != "output"}
        if self.config.get("output") == output:
            self.config.update(self.current_colors())
        save_config(self.config)
        self.color_status.set_text("Enregistrement et application…")
        self.run_color_controller(output)

    def cancel_color_preview(self, _button):
        self.load_color_controls()
        self.color_status.set_text("Aperçu annulé; profil enregistré restauré.")
        self.run_color_controller(self.selected_color_output())

    def build_discover_view(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                       margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)
        navigation = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        back = Gtk.Button(icon_name="go-previous-symbolic", tooltip_text="Page précédente")
        back.connect("clicked", lambda _button: self.web_view.go_back())
        navigation.append(back)
        forward = Gtk.Button(icon_name="go-next-symbolic", tooltip_text="Page suivante")
        forward.connect("clicked", lambda _button: self.web_view.go_forward())
        navigation.append(forward)
        reload_button = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Actualiser la page")
        reload_button.connect("clicked", lambda _button: self.web_view.reload())
        navigation.append(reload_button)

        self.source_names = list(WALLPAPER_SOURCES)
        sources = Gtk.DropDown.new_from_strings(self.source_names)
        sources.set_tooltip_text("Catalogue de fonds vidéo")
        sources.connect("notify::selected", self.source_changed)
        navigation.append(sources)
        self.web_address = Gtk.Entry(hexpand=True, placeholder_text="Rechercher ou saisir une adresse")
        self.web_address.connect("activate", self.open_web_address)
        navigation.append(self.web_address)
        download_button = Gtk.Button(icon_name="document-save-symbolic",
                                     tooltip_text="Télécharger la vidéo de cette page")
        download_button.connect("clicked", self.download_current_page)
        navigation.append(download_button)
        self.adblock_button = Gtk.ToggleButton(icon_name="security-high-symbolic",
                                               tooltip_text="Bloqueur de publicités actif")
        self.adblock_button.set_active(True)
        self.adblock_button.connect("toggled", self.adblock_toggled)
        navigation.append(self.adblock_button)
        page.append(navigation)

        self.web_content = WebKit.UserContentManager()
        self.adblock_style = WebKit.UserStyleSheet.new(
            ADBLOCK_CSS, WebKit.UserContentInjectedFrames.ALL_FRAMES,
            WebKit.UserStyleLevel.USER, None, None,
        )
        self.adblock_filter = None
        self.web_content.add_style_sheet(self.adblock_style)
        self.compile_adblock_filter()
        self.web_view = WebKit.WebView(user_content_manager=self.web_content)
        self.web_view.set_vexpand(True)
        self.web_view.connect("notify::uri", self.web_uri_changed)
        self.web_view.connect("load-changed", self.web_load_changed)
        self.web_view.connect("decide-policy", self.web_decide_policy)
        WebKit.NetworkSession.get_default().connect("download-started", self.download_started)
        page.append(self.web_view)
        self.download_status = Gtk.Label(
            label="Les vidéos téléchargées apparaissent automatiquement dans la bibliothèque.",
            xalign=0, ellipsize=3, css_classes=["dim-label"],
        )
        page.append(self.download_status)
        self.web_view.load_uri(WALLPAPER_SOURCES[self.source_names[0]])
        return page

    def theme_dropdown(self, parent, title, values, current):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(Gtk.Label(label=title, xalign=0, css_classes=["heading"]))
        dropdown = Gtk.DropDown.new_from_strings(values)
        dropdown.set_selected(values.index(current) if current in values else 0)
        box.append(dropdown)
        parent.append(box)
        return dropdown

    def build_themes_view(self):
        scroll = Gtk.ScrolledWindow(vexpand=True)
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                       margin_top=22, margin_bottom=22, margin_start=24, margin_end=24)
        page.set_size_request(520, -1)
        page.append(Gtk.Label(label="Apparence du bureau", xalign=0,
                              css_classes=["title-2"]))
        page.append(Gtk.Label(
            label="Choisissez les thèmes utilisés par les applications GTK de votre session.",
            xalign=0, wrap=True, css_classes=["dim-label"],
        ))

        self.color_modes = ["Clair", "Sombre", "Selon le système"]
        schemes = {"prefer-light": "Clair", "prefer-dark": "Sombre",
                   "default": "Selon le système"}
        current_scheme = schemes.get(
            desktop_interface_setting("color-scheme", "default"), "Selon le système"
        )
        self.theme_color = self.theme_dropdown(
            page, "Mode de couleur", self.color_modes, current_scheme
        )

        current_gtk = desktop_interface_setting("gtk-theme", "Adwaita")
        self.gtk_themes = installed_appearance_items("gtk") or ["Adwaita"]
        if current_gtk not in self.gtk_themes:
            self.gtk_themes.insert(0, current_gtk)
        self.theme_gtk = self.theme_dropdown(
            page, "Thème GTK", self.gtk_themes, current_gtk,
        )
        current_icons = desktop_interface_setting("icon-theme", "Adwaita")
        self.icon_themes = installed_appearance_items("icons") or ["Adwaita"]
        if current_icons not in self.icon_themes:
            self.icon_themes.insert(0, current_icons)
        self.theme_icons = self.theme_dropdown(
            page, "Icônes", self.icon_themes, current_icons,
        )
        current_cursor = desktop_interface_setting("cursor-theme", "default")
        self.cursor_themes = installed_appearance_items("cursors") or ["default"]
        if current_cursor not in self.cursor_themes:
            self.cursor_themes.insert(0, current_cursor)
        self.theme_cursor = self.theme_dropdown(
            page, "Curseur", self.cursor_themes, current_cursor,
        )

        apply_button = Gtk.Button(label="Appliquer le thème",
                                  css_classes=["suggested-action"])
        apply_button.connect("clicked", self.apply_theme)
        page.append(apply_button)

        page.append(Gtk.Separator(margin_top=12, margin_bottom=2))
        theme_heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        theme_heading.append(Gtk.Label(label="Thèmes Debian V2", xalign=0,
                                       hexpand=True, css_classes=["title-3"]))
        self.v2_theme_count = Gtk.Label(label="0 thèmes", xalign=1,
                                        css_classes=["dim-label"])
        theme_heading.append(self.v2_theme_count)
        page.append(theme_heading)
        theme_search = Gtk.SearchEntry(placeholder_text="Rechercher un thème",
                                       search_delay=120)
        theme_search.set_tooltip_text("Filtrer les thèmes Debian V2")
        page.append(theme_search)
        theme_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                                  css_classes=["boxed-list"])
        theme_list.set_margin_top(2)
        available_v2_themes = v2_themes()
        self.v2_theme_rows = []
        self.v2_theme_count.set_text(f"{len(available_v2_themes)} thèmes")
        if available_v2_themes:
            for theme_id, theme_name, mode in available_v2_themes:
                row = Adw.ActionRow(title=theme_name,
                                    subtitle=f"{theme_id}  ·  {'Clair' if mode == 'light' else 'Sombre'}")
                row.theme_search_text = f"{theme_id} {theme_name} {mode}".casefold()
                row.add_prefix(Gtk.Image.new_from_icon_name("applications-graphics-symbolic"))
                apply_v2_button = Gtk.Button(label="Appliquer",
                                             css_classes=["suggested-action"],
                                             valign=Gtk.Align.CENTER)
                apply_v2_button.connect(
                    "clicked", self.apply_v2_theme,
                    theme_id, theme_name, apply_v2_button,
                )
                row.add_suffix(apply_v2_button)
                theme_list.append(row)
                self.v2_theme_rows.append(row)
        else:
            theme_list.append(Gtk.Label(
                label="Catalogue V2 introuvable. Vérifiez le chemin du dépôt.",
                margin_top=12, margin_bottom=12,
            ))
        theme_search.connect("search-changed", self.filter_v2_themes)
        page.append(theme_list)
        self.theme_status = Gtk.Label(label="", xalign=0, wrap=True,
                                      css_classes=["dim-label"])
        page.append(self.theme_status)
        scroll.set_child(page)
        return scroll

    def filter_v2_themes(self, entry):
        query = entry.get_text().casefold().strip()
        for row in self.v2_theme_rows:
            row.set_visible(not query or query in row.theme_search_text)

    def apply_theme(self, _button):
        settings = Gio.Settings.new("org.gnome.desktop.interface")
        mode = self.color_modes[self.theme_color.get_selected()]
        scheme = {"Clair": "prefer-light", "Sombre": "prefer-dark",
                  "Selon le système": "default"}[mode]
        values = {
            "color-scheme": scheme,
            "gtk-theme": self.gtk_themes[self.theme_gtk.get_selected()],
            "icon-theme": self.icon_themes[self.theme_icons.get_selected()],
            "cursor-theme": self.cursor_themes[self.theme_cursor.get_selected()],
        }
        try:
            for key, value in values.items():
                settings.set_string(key, value)
            write_gtk_theme_settings(values, mode == "Sombre")
            Adw.StyleManager.get_default().set_color_scheme(
                Adw.ColorScheme.FORCE_DARK if mode == "Sombre"
                else Adw.ColorScheme.FORCE_LIGHT if mode == "Clair"
                else Adw.ColorScheme.DEFAULT
            )
            self.theme_status.set_text(
                f"Thème {values['gtk-theme']} appliqué avec les icônes "
                f"{values['icon-theme']}."
            )
        except GLib.Error as error:
            self.theme_status.set_text(f"Impossible d’appliquer le thème : {error.message}")

    def apply_v2_theme(self, _button, theme_id, theme_name, button):
        if not V2_INSTALLER.is_file():
            self.theme_status.set_text(
                f"Installateur V2 introuvable : {V2_INSTALLER}"
            )
            return
        button.set_sensitive(False)
        self.theme_status.set_text(f"Application du thème V2 {theme_name}…")

        def worker():
            result = bounded_process(
                ["bash", str(V2_INSTALLER), "theme", "apply", theme_id],
                timeout=900, capture_output=True, text=True,
            )
            GLib.idle_add(self.v2_theme_finished, result, theme_name, button)

        threading.Thread(target=worker, daemon=True).start()

    def v2_theme_finished(self, result, theme_name, button):
        button.set_sensitive(True)
        if result.returncode == 0:
            self.theme_status.set_text(
                f"Thème V2 {theme_name} appliqué. Hyprland a été rechargé."
            )
        else:
            detail = result.stderr.strip().splitlines()
            self.theme_status.set_text(
                detail[-1] if detail else f"Impossible d’appliquer {theme_name}."
            )
        return False

    def compile_adblock_filter(self):
        rules = [
            {
                "trigger": {"url-filter": f".*{domain.replace('.', r'\.')}.*"},
                "action": {"type": "block"},
            }
            for domain in AD_DOMAINS
        ]
        store = WebKit.UserContentFilterStore.new(str(CACHE_DIR.parent / "adblock"))
        store.save(
            "mpvpaper-engine-ads", GLib.Bytes.new(json.dumps(rules).encode()),
            None, self.adblock_filter_ready,
        )

    def adblock_filter_ready(self, store, result):
        try:
            self.adblock_filter = store.save_finish(result)
        except GLib.Error as error:
            self.download_status.set_text(f"Bloqueur réseau indisponible : {error.message}")
            return
        if self.adblock_button.get_active():
            self.web_content.add_filter(self.adblock_filter)
            self.web_view.reload()

    def adblock_toggled(self, button):
        self.web_content.remove_all_filters()
        self.web_content.remove_all_style_sheets()
        if button.get_active():
            self.web_content.add_style_sheet(self.adblock_style)
            if self.adblock_filter:
                self.web_content.add_filter(self.adblock_filter)
            button.set_tooltip_text("Bloqueur de publicités actif")
            self.download_status.set_text("Protection contre les publicités activée")
        else:
            button.set_tooltip_text("Bloqueur de publicités désactivé")
            self.download_status.set_text("Protection contre les publicités désactivée")
        self.web_view.reload()

    def build_suggestions_view(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                       margin_top=16, margin_bottom=16, margin_start=18, margin_end=18)
        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        heading.append(Gtk.Label(label="Pour vous", xalign=0, hexpand=True,
                                 css_classes=["title-2"]))
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Recalculer les suggestions")
        refresh.connect("clicked", lambda _button: self.refresh_suggestions())
        heading.append(refresh)
        page.append(heading)
        self.suggestion_hint = Gtk.Label(
            label="Mode Pinterest · faites défiler pour charger automatiquement la suite.",
            xalign=0, wrap=True, css_classes=["dim-label"],
        )
        page.append(self.suggestion_hint)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        self.suggestion_flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                                           column_spacing=14, row_spacing=14,
                                           min_children_per_line=2, max_children_per_line=4)
        self.suggestion_flow.set_valign(Gtk.Align.START)
        scroll.set_child(self.suggestion_flow)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_kinetic_scrolling(True)
        scroll.connect("edge-reached", self.suggestion_edge_reached)
        scroll.get_vadjustment().connect("value-changed", self.suggestion_scroll_changed)
        self.suggestion_scroll = scroll
        page.append(scroll)
        return page

    def view_changed(self, stack, _property):
        if stack.get_visible_child_name() == "suggestions":
            self.refresh_suggestions()

    def refresh_suggestions(self):
        while child := self.suggestion_flow.get_first_child():
            self.suggestion_flow.remove(child)
        self.suggestion_feed_uris = []
        self.suggestion_feed_fingerprints = set()
        self.suggestion_cards = {}
        self.load_more_suggestions()

    def suggestion_edge_reached(self, _scroll, position):
        if position == Gtk.PositionType.BOTTOM:
            self.schedule_more_suggestions()

    def suggestion_scroll_changed(self, adjustment):
        if self.suggestion_seed_update_id is None:
            self.suggestion_seed_update_id = GLib.timeout_add(
                120, self.update_visible_suggestion_seed
            )
        remaining = adjustment.get_upper() - (
            adjustment.get_value() + adjustment.get_page_size()
        )
        if remaining <= 360:
            self.schedule_more_suggestions()

    def update_visible_suggestion_seed(self):
        adjustment = self.suggestion_scroll.get_vadjustment()
        center_x = self.suggestion_scroll.get_allocated_width() // 2
        center_y = int(adjustment.get_value() + adjustment.get_page_size() / 2)
        child = self.suggestion_flow.get_child_at_pos(center_x, center_y)
        if child is not None and hasattr(child, "suggestion_uri"):
            self.suggestion_seed_uri = child.suggestion_uri
        self.suggestion_seed_update_id = None
        return False

    def schedule_more_suggestions(self):
        if self.suggestion_loading:
            return
        self.suggestion_loading = True
        GLib.idle_add(self.load_suggestion_batch)

    def load_suggestion_batch(self):
        try:
            self.load_more_suggestions()
        finally:
            self.suggestion_loading = False
        return False

    def suggestion_batch_size(self):
        width = max(1, self.suggestion_scroll.get_allocated_width())
        height = max(1, int(self.suggestion_scroll.get_vadjustment().get_page_size()))
        columns = max(2, min(4, width // 280))
        rows = max(1, math.ceil((height + 360) / 220))
        return columns * rows

    def load_more_suggestions(self):
        batch_size = self.suggestion_batch_size()
        recommendations = self.taste.recommendations(
            limit=batch_size,
            exclude_fingerprints=self.suggestion_feed_fingerprints,
            seed_uri=self.suggestion_seed_uri,
        )
        if not recommendations:
            if self.refresh_suggestion_sources():
                return
        recommendations = [
            item for item in recommendations
            if content_fingerprint(item[1], item[2]) not in self.suggestion_feed_fingerprints
        ]
        current_uris = [item[1] for item in recommendations]
        self.taste.record_impressions(recommendations)
        save_suggestion_history(self.displayed_suggestion_uris, current_uris)
        self.displayed_suggestion_uris = load_suggestion_history()
        self.suggestion_feed_uris.extend(current_uris)
        self.suggestion_feed_fingerprints.update(
            content_fingerprint(item[1], item[2]) for item in recommendations
        )
        if not recommendations:
            if not self.suggestion_feed_uris:
                self.suggestion_hint.set_text(
                    "Parcourez quelques fonds dans Découvrir pour initialiser vos suggestions."
                )
            else:
                self.suggestion_hint.set_text(
                    "Recherche automatique de nouveaux contenus…"
                )
                self.schedule_suggestion_source_retry()
            return
        self.suggestion_hint.set_text(
            "Flux continu personnalisé · faites défiler pour charger la suite."
        )
        missing = []
        for (score, uri, title, source, tags, rating, confidence,
             external_views, external_likes) in recommendations:
            thumbnail = suggestion_thumbnail_path(uri)
            card = SuggestionCard(
                title, source, tags, rating, confidence, thumbnail,
                external_views, external_likes,
                lambda _button, target=uri: self.open_suggestion(_button, target),
                lambda _button, target=uri, label=title: self.favorite_suggestion(target, label),
            )
            card.suggestion_uri = uri
            self.suggestion_flow.append(card)
            self.suggestion_cards.setdefault(uri, []).append(card)
            if not thumbnail.exists() and uri not in self.suggestion_thumbnail_attempted:
                self.suggestion_thumbnail_attempted.add(uri)
                missing.append((uri, thumbnail))
        if missing:
            threading.Thread(target=self.generate_suggestion_thumbnails,
                             args=(missing,), daemon=True).start()
        GLib.idle_add(self.ensure_suggestion_feed_filled)

    def refresh_suggestion_sources(self):
        now = time.monotonic()
        if self.source_refreshing:
            return True
        elapsed = now - self.last_source_refresh
        if elapsed < SOURCE_REFRESH_INTERVAL:
            self.schedule_suggestion_source_retry(
                max(1, math.ceil(SOURCE_REFRESH_INTERVAL - elapsed))
            )
            return True
        self.source_refreshing = True
        self.last_source_refresh = now
        self.source_refresh_before = self.taste.candidate_count()
        self.source_refresh_wanted = max(1, self.suggestion_batch_size())
        self.suggestion_hint.set_text("Recherche de nouvelles propositions dans les sources…")
        threading.Thread(target=self.fetch_suggestion_sources, daemon=True).start()
        return True

    def fetch_suggestion_sources(self):
        prefetch_suggestions(desired_new=self.source_refresh_wanted)
        GLib.idle_add(self.suggestion_sources_ready)

    def suggestion_sources_ready(self):
        added = self.taste.candidate_count() - self.source_refresh_before
        self.source_refreshing = False
        if added:
            self.source_retry_delay = SOURCE_REFRESH_INTERVAL
            self.suggestion_hint.set_text(f"{added} nouvelles propositions trouvées.")
            self.schedule_more_suggestions()
        else:
            self.suggestion_hint.set_text(
                "Sources à jour · nouvelle exploration automatique en arrière-plan."
            )
            self.schedule_suggestion_source_retry(self.source_retry_delay)
            self.source_retry_delay = min(self.source_retry_delay * 2, 300)
        return False

    def schedule_suggestion_source_retry(self, delay=None):
        if self.source_retry_id is not None:
            return
        self.source_retry_id = GLib.timeout_add_seconds(
            max(1, int(delay or self.source_retry_delay)),
            self.retry_suggestion_sources,
        )

    def retry_suggestion_sources(self):
        self.source_retry_id = None
        self.last_source_refresh = 0.0
        self.schedule_more_suggestions()
        return False

    def ensure_suggestion_feed_filled(self):
        adjustment = self.suggestion_scroll.get_vadjustment()
        if adjustment.get_upper() <= adjustment.get_page_size() + 360:
            self.schedule_more_suggestions()
        return False

    def generate_suggestion_thumbnails(self, items):
        for uri, destination in items:
            if fetch_suggestion_thumbnail(uri, destination):
                GLib.idle_add(self.suggestion_thumbnail_ready, uri, destination)

    def suggestion_thumbnail_ready(self, uri, destination):
        for card in self.suggestion_cards.get(uri, []):
            card.picture.set_filename(str(destination))
        return False

    def favorite_suggestion(self, uri, title):
        self.taste.record(uri, title, 4.0, candidate=True)
        self.suggestion_seed_uri = uri
        self.refresh_suggestions()

    def open_suggestion(self, _button, uri):
        self.suggestion_seed_uri = uri
        self.views.set_visible_child_name("discover")
        self.web_view.load_uri(uri)

    def source_changed(self, dropdown, _property):
        self.web_view.load_uri(WALLPAPER_SOURCES[self.source_names[dropdown.get_selected()]])

    def open_web_address(self, entry):
        value = entry.get_text().strip()
        if not value:
            return
        if value.startswith(("https://", "http://")):
            uri = value
        elif "." in value and " " not in value:
            uri = "https://" + value
        else:
            uri = "https://duckduckgo.com/?q=" + quote_plus(value + " live wallpaper mp4")
        self.web_view.load_uri(uri)

    def web_uri_changed(self, web_view, _property):
        self.web_address.set_text(web_view.get_uri() or "")

    def web_load_changed(self, web_view, event):
        if event == WebKit.LoadEvent.FINISHED:
            title = web_view.get_title() or "Page chargée"
            self.download_status.set_text(title)
            self.taste.record(web_view.get_uri(), title, 0.15)

    def web_decide_policy(self, _web_view, decision, decision_type):
        if decision_type != WebKit.PolicyDecisionType.NEW_WINDOW_ACTION:
            return False
        action = decision.get_navigation_action()
        if action.is_user_gesture():
            self.web_view.load_uri(action.get_request().get_uri())
        decision.ignore()
        return True

    def download_current_page(self, _button):
        uri = self.web_view.get_uri()
        if not uri:
            return
        self.download_status.set_text("Recherche de la vidéo sur cette page…")
        title = (self.web_view.get_title() or "fond-video").replace("/", "-")

        def worker():
            download_uri = page_download_url(uri)
            result = bounded_process(
                [
                    str(LOCAL_YTDLP) if LOCAL_YTDLP.is_file() else "yt-dlp",
                    "--no-playlist", "--no-progress",
                    "--print", "after_move:filepath",
                    "-o", str(LIBRARY_DIR / f"{title[:160]}.%(ext)s"), download_uri,
                ],
                timeout=1800, capture_output=True, text=True,
            )
            GLib.idle_add(self.page_download_finished, result)

        threading.Thread(target=worker, daemon=True).start()

    def page_download_finished(self, result):
        if result.returncode == 0:
            paths = [line for line in result.stdout.splitlines() if line.strip()]
            name = Path(paths[-1]).name if paths else "vidéo"
            self.download_status.set_text(f"Ajouté à la bibliothèque : {name}")
            self.taste.record(self.web_view.get_uri(), self.web_view.get_title() or name, 2.0,
                              candidate=True)
            self.load_library()
        else:
            message = result.stderr.strip().splitlines()
            detail = message[-1] if message else "aucune vidéo détectée"
            self.download_status.set_text(f"Téléchargement impossible : {detail}")

    def download_started(self, _session, download):
        download.connect("decide-destination", self.choose_download_destination)
        download.connect("notify::estimated-progress", self.download_progress)
        download.connect("finished", self.download_finished)
        download.connect("failed", self.download_failed)

    def choose_download_destination(self, download, suggested_name):
        name = Path(suggested_name or "fond-video.mp4").name
        destination = LIBRARY_DIR / name
        counter = 2
        while destination.exists():
            destination = LIBRARY_DIR / f"{Path(name).stem}-{counter}{Path(name).suffix}"
            counter += 1
        download.set_destination(str(destination))
        self.download_status.set_text(f"Téléchargement : {destination.name}")
        return True

    def download_progress(self, download, _property):
        progress = int(download.get_estimated_progress() * 100)
        self.download_status.set_text(f"Téléchargement en cours : {progress} %")

    def download_finished(self, download):
        destination = Path(download.get_destination())
        self.download_status.set_text(f"Ajouté à la bibliothèque : {destination.name}")
        self.taste.record(self.web_view.get_uri(), self.web_view.get_title() or destination.name,
                          2.0, candidate=True)
        self.load_library()

    def download_failed(self, _download, error):
        self.download_status.set_text(f"Échec du téléchargement : {error.message}")

    def switch_row(self, title, subtitle, active):
        row = Adw.ActionRow(title=title, subtitle=subtitle)
        switch = Gtk.Switch(active=active, valign=Gtk.Align.CENTER)
        row.add_suffix(switch)
        row.set_activatable_widget(switch)
        return row, switch

    def videos(self):
        videos = set()
        for directory in (LIBRARY_DIR, LEGACY_LIBRARY_DIR):
            if directory.is_dir():
                videos.update(
                    path.resolve() for path in directory.rglob("*")
                    if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
                )
        return sorted(videos, key=lambda path: path.name.lower())

    def load_metadata(self):
        try:
            return json.loads(METADATA_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def save_metadata(self):
        METADATA_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write_text(METADATA_FILE, json.dumps(self.metadata, indent=2) + "\n")

    def load_library(self):
        while child := self.flow.get_first_child():
            self.flow.remove(child)
        self.cards = []
        missing = []
        for video in self.videos():
            thumb = thumbnail_path(video)
            key = metadata_key(video)
            card = WallpaperCard(video, thumb, self.metadata.get(key, "Analyse en cours…"))
            self.cards.append(card)
            self.flow.append(card)
            if not thumb.exists() or key not in self.metadata:
                missing.append((video, thumb, key))
            if self.selected and video.resolve() == self.selected.expanduser().resolve():
                self.flow.select_child(card)
        if missing:
            threading.Thread(target=self.generate_thumbnails, args=(missing,), daemon=True).start()

    def generate_thumbnails(self, items):
        for video, thumb, key in items:
            if not thumb.exists():
                bounded_process(
                    ["ffmpegthumbnailer", "-i", str(video), "-o", str(thumb),
                     "-s", "480", "-t", "20"],
                    timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            if key not in self.metadata:
                self.metadata[key] = probe_video_duration(video)
        self.save_metadata()
        GLib.idle_add(self.load_library)

    def filter_library(self, entry):
        query = entry.get_text().casefold()
        for card in self.cards:
            card.set_visible(query in card.path.stem.casefold())

    def selection_changed(self, flow):
        selected = flow.get_selected_children()
        if not selected:
            return
        self.selected = selected[0].path
        self.selected_label.set_text(self.selected.name)
        self.apply_button.set_sensitive(True)
        self.login_button.set_sensitive(True)

    def output_changed(self, dropdown, _property):
        output = self.output_names[dropdown.get_selected()]
        profile = self.config.get("assignments", {}).get(output)
        if not profile:
            self.status.set_text(f"Aucun fond attribué à {output}")
            return
        wallpaper = Path(profile.get("wallpaper", ""))
        self.selected = wallpaper if wallpaper.is_file() else None
        self.selected_label.set_text(wallpaper.name if self.selected else "Sélectionnez une vidéo")
        self.volume.set_value(profile.get("volume", 0))
        speed = float(profile.get("speed", 1.0))
        self.speed.set_selected(self.speeds.index(speed) if speed in self.speeds else 2)
        self.loop[1].set_active(profile.get("loop", True))
        self.hardware[1].set_active(profile.get("hardware_decode", True))
        self.auto_pause[1].set_active(profile.get("auto_pause", True))
        self.autostart[1].set_active(profile.get("autostart", True))
        self.apply_button.set_sensitive(self.selected is not None)
        self.login_button.set_sensitive(self.selected is not None)
        for card in self.cards:
            if self.selected and card.path.resolve() == self.selected.resolve():
                self.flow.select_child(card)
                break

    def import_videos(self, _button):
        dialog = Gtk.FileDialog(title="Importer des fonds vidéo", modal=True)
        video_filter = Gtk.FileFilter(name="Vidéos")
        for mime in ("video/mp4", "video/webm", "video/x-matroska", "video/quicktime", "video/x-msvideo"):
            video_filter.add_mime_type(mime)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(video_filter)
        dialog.set_filters(filters)
        dialog.open_multiple(self, None, self.import_finished)

    def import_youtube(self, _button):
        dialog = Gtk.Window(title="Importer depuis YouTube", transient_for=self,
                            modal=True, default_width=480, resizable=False)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                          margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        content.append(Gtk.Label(label="Vidéo YouTube", xalign=0, css_classes=["title-2"]))
        url_entry = Gtk.Entry(placeholder_text="https://www.youtube.com/watch?v=…")
        content.append(url_entry)
        quality_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        quality_box.append(Gtk.Label(label="Qualité", xalign=0, hexpand=True))
        quality = Gtk.DropDown.new_from_strings(["1080p", "1440p", "2160p (4K)"])
        quality.set_selected(2)
        quality_box.append(quality)
        content.append(quality_box)
        error = Gtk.Label(label="", xalign=0, wrap=True, css_classes=["error"])
        content.append(error)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                          halign=Gtk.Align.END)
        cancel = Gtk.Button(label="Annuler")
        cancel.connect("clicked", lambda _button: dialog.close())
        actions.append(cancel)
        download = Gtk.Button(label="Télécharger", css_classes=["suggested-action"])

        def start(_button):
            uri = url_entry.get_text().strip()
            if not is_youtube_url(uri):
                error.set_text("Adresse YouTube invalide")
                return
            heights = (1080, 1440, 2160)
            dialog.close()
            self.start_youtube_download(uri, heights[quality.get_selected()])

        download.connect("clicked", start)
        url_entry.connect("activate", start)
        actions.append(download)
        content.append(actions)
        dialog.set_child(content)
        dialog.present()
        url_entry.grab_focus()

    def start_youtube_download(self, uri, height):
        self.views.set_visible_child_name("library")
        self.status.set_text(f"Téléchargement YouTube en {height}p…")

        def worker():
            result = bounded_process(
                youtube_download_command(uri, height),
                timeout=1800, capture_output=True, text=True,
            )
            GLib.idle_add(self.youtube_download_finished, uri, result)

        threading.Thread(target=worker, daemon=True).start()

    def youtube_download_finished(self, uri, result):
        paths = [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]
        if result.returncode != 0 or not paths or not paths[-1].is_file():
            messages = [line for line in result.stderr.splitlines() if line.strip()]
            detail = messages[-1] if messages else "Téléchargement YouTube impossible"
            self.status.set_text(detail)
            return
        self.selected = paths[-1]
        self.taste.record(uri, self.selected.stem, 2.0, candidate=True)
        self.load_library()
        self.selected_label.set_text(self.selected.name)
        self.apply_button.set_sensitive(True)
        self.login_button.set_sensitive(True)
        self.status.set_text(f"Vidéo YouTube prête : {self.selected.name}")

    def import_finished(self, dialog, result):
        try:
            files = dialog.open_multiple_finish(result)
        except GLib.Error:
            return
        for item in files:
            source = Path(item.get_path())
            destination = LIBRARY_DIR / source.name
            counter = 2
            while destination.exists() and destination.resolve() != source.resolve():
                destination = LIBRARY_DIR / f"{source.stem}-{counter}{source.suffix}"
                counter += 1
            if source.resolve() != destination.resolve():
                shutil.copy2(source, destination)
        self.load_library()

    def current_config(self):
        output = self.output_names[self.output.get_selected()]
        colors = {
            **COLOR_DEFAULTS,
            **self.config.get("assignments", {}).get(output, {}),
        }
        if self.selected_color_output() == output:
            colors.update(self.current_colors())
        return {
            "wallpaper": str(self.selected) if self.selected else "",
            "output": output,
            "volume": int(self.volume.get_value()),
            "speed": self.speeds[self.speed.get_selected()],
            "loop": self.loop[1].get_active(),
            "hardware_decode": self.hardware[1].get_active(),
            "auto_pause": self.auto_pause[1].get_active(),
            "autostart": self.autostart[1].get_active(),
            **{key: colors[key] for key in COLOR_DEFAULTS},
        }

    def run_controller(self, action, callback=None):
        def worker():
            result = bounded_process(
                [str(CONTROLLER), action], timeout=30, capture_output=True, text=True,
            )
            GLib.idle_add(callback or self.command_finished, action, result)
        threading.Thread(target=worker, daemon=True).start()

    def apply_wallpaper(self, _button):
        if not self.selected:
            return
        profile = self.current_config()
        output = profile["output"]
        assignments = self.config.setdefault("assignments", {})
        if output == "*":
            assignments.clear()
        else:
            assignments.pop("*", None)
        assignments[output] = {key: value for key, value in profile.items() if key != "output"}
        self.config.update(profile)
        save_config(self.config)
        self.taste.reinforce(self.selected.stem, 3.0)
        self.apply_button.set_sensitive(False)
        self.status.set_text("Application du fond vidéo…")
        self.run_controller("play")

    def stop_wallpaper(self, _button):
        self.status.set_text("Arrêt du fond vidéo…")
        self.run_controller("stop")

    def set_login_wallpaper(self, _button):
        if not self.selected:
            return
        self.login_button.set_sensitive(False)
        self.status.set_text("Extraction de l’image de connexion…")

        def worker():
            output = CACHE_DIR.parent / "login-background.jpeg"
            extract = bounded_process(
                ["ffmpegthumbnailer", "-i", str(self.selected), "-o", str(output),
                 "-s", "1920", "-t", "20"],
                timeout=120, capture_output=True, text=True,
            )
            if extract.returncode == 0:
                result = subprocess.run(
                    [
                        "kitty", "--class", "mpvpaper-sddm-auth",
                        "--title", "Autorisation SDDM",
                        "bash", "-lc",
                        'printf "Mot de passe administrateur requis pour modifier l écran de connexion.\\n"; '
                        'sudo "$1" "$2"',
                        "mpvpaper-sddm-auth", str(SDDM_INSTALLER), str(output),
                    ],
                    capture_output=True, text=True, check=False,
                )
            else:
                result = extract
            GLib.idle_add(self.login_wallpaper_finished, result)

        threading.Thread(target=worker, daemon=True).start()

    def login_wallpaper_finished(self, result):
        self.login_button.set_sensitive(self.selected is not None)
        if result.returncode == 0:
            self.status.set_text("Fond de connexion installé. Il apparaîtra au prochain démarrage.")
        else:
            self.status.set_text("Installation annulée ou mot de passe incorrect")

    def command_finished(self, action, result):
        self.apply_button.set_sensitive(self.selected is not None)
        if result.returncode == 0:
            self.status.set_text("Fond vidéo actif sur " + self.config.get("output", "*") if action == "play" else "Fond vidéo arrêté")
        else:
            message = result.stderr.strip() or "La commande a échoué"
            self.status.set_text(message)

    def refresh_status(self):
        self.run_controller("status", self.status_finished)
        return False

    def status_finished(self, _action, result):
        state = result.stdout.strip()
        if state.startswith("active:"):
            count = state.partition(":")[2]
            self.status.set_text(f"Fonds actifs sur {count} écran(s)")
        else:
            self.status.set_text("Aucun fond vidéo actif")


class MPVpaperApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)

    def do_startup(self):
        Adw.Application.do_startup(self)
        css = Gtk.CssProvider()
        css.load_from_string("""
            window { background: #111216; color: #f5f6f8; }
            headerbar { background: #17191f; color: #f5f6f8; }
            label { color: #f5f6f8; }
            label.dim-label, label.secondary-text, .subtitle { color: #c8ccd6; }
            entry, searchentry, dropdown, button { color: #f5f6f8; }
            entry, searchentry, dropdown { background: #292c34; }
            actionrow { color: #f5f6f8; }
            .wallpaper-card { padding: 8px; border-radius: 6px; background: #1b1e25; border: 1px solid #30343e; }
            .wallpaper-card:hover { background: #242832; border-color: #e23864; }
            flowboxchild:selected .wallpaper-card { background: #302028; border-color: #ff5277; }
            .card-title { font-weight: 700; }
            .suggestion-card { padding: 10px; border-radius: 6px; background: #1b1e25; border: 1px solid #30343e; }
            .suggestion-card:hover { background: #242832; border-color: #4f8cff; }
            .suggestion-source { color: #6da2ff; font-weight: 600; }
            .suggestion-rating { color: #f3c969; }
            picture { border-radius: 4px; background: #090a0d; }
        """)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        window = self.props.active_window or MPVpaperWindow(self)
        window.present()

    def do_command_line(self, command_line):
        arguments = command_line.get_arguments()
        self.activate()
        window = self.props.active_window
        if window and "--colors" in arguments:
            window.views.set_visible_child_name("colors")
        return 0

    def do_shutdown(self):
        bounded_process(
            ["systemctl", "--user", "start", "--no-block",
             "mpvpaper-engine-prefetch.service"],
            timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        Adw.Application.do_shutdown(self)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--prefetch":
        desired = int(sys.argv[2]) if len(sys.argv) >= 3 else None
        raise SystemExit(prefetch_suggestions(
            desired_new=max(1, desired) if desired is not None else None
        ))
    if len(sys.argv) >= 2 and sys.argv[1] == "--prefetch-continuous":
        raise SystemExit(prefetch_suggestions(page_budget=SOURCE_CRAWL_SLICE))
    if len(sys.argv) >= 2 and sys.argv[1] == "--prefetch-all":
        raise SystemExit(prefetch_suggestions())
    raise SystemExit(MPVpaperApplication().run())
