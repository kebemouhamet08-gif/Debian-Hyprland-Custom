#!/usr/bin/env python3

import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import threading
import time
from urllib.parse import quote_plus, urljoin
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
LIBRARY_DIR = Path.home() / "Pictures" / "Wallpapers" / "Live"
LEGACY_LIBRARY_DIR = Path.home() / "Pictures" / "wallpapers"
CONTROLLER = Path.home() / ".local" / "lib" / "mpvpaper-engine" / "mpvpaper-enginectl.py"
SDDM_INSTALLER = Path.home() / ".local" / "lib" / "mpvpaper-engine" / "install-sddm-background.sh"
DEFAULT_CONFIG = {
    "wallpaper": "", "output": "*", "volume": 0, "speed": 1.0,
    "loop": True, "hardware_decode": True, "auto_pause": True, "autostart": True,
}
WALLPAPER_SOURCES = {
    "Steam Workshop": "https://steamcommunity.com/workshop/browse?appid=431960",
    "MotionBGS": "https://motionbgs.com/",
    "MoeWalls": "https://moewalls.com/",
    "VSThemes": "https://vsthemes.org/en/wallpapers/page/4/",
}
DEFAULT_SUGGESTIONS = (
    ("https://steamcommunity.com/workshop/browse?appid=431960", "Tendances Wallpaper Engine Workshop", "steamcommunity.com", "workshop trending community"),
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
    ("https://vsthemes.org/en/wallpapers/page/4/", "Sélection animée VSThemes - page 4", "vsthemes.org", "collection animated discovery"),
    ("https://vsthemes.org/en/wallpapers/", "Nouveautés animées VSThemes", "vsthemes.org", "collection new discovery"),
)
SOURCE_PRIORITY = {
    "steamcommunity.com": 0,
    "motionbgs.com": 1,
    "moewalls.com": 2,
    "vsthemes.org": 3,
}
TAG_STOPWORDS = {
    "wallpaper", "live", "animated", "background", "video", "fond", "ecran",
    "the", "and", "for", "with", "from", "page", "https", "www", "com",
    "motionbgs", "moewalls", "vsthemes", "html", "en",
}


def content_tags(*values):
    words = re.findall(r"[a-z0-9]+", " ".join(values).casefold())
    return sorted({word for word in words if len(word) > 2 and word not in TAG_STOPWORDS})[:16]


class TasteStore:
    def __init__(self, path=TASTE_DB):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA cache_size=-2000")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS candidates (
                uri TEXT PRIMARY KEY, title TEXT NOT NULL, source TEXT NOT NULL,
                tags TEXT NOT NULL, score REAL NOT NULL DEFAULT 0,
                views INTEGER NOT NULL DEFAULT 0, last_seen INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tag_profile (
                tag TEXT PRIMARY KEY, weight REAL NOT NULL DEFAULT 0
            );
        """)
        self.connection.executemany(
            "DELETE FROM candidates WHERE uri = ?",
            ((uri,) for uri in WALLPAPER_SOURCES.values()),
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

    def reinforce(self, title, weight):
        for tag in content_tags(title):
            self.connection.execute(
                """INSERT INTO tag_profile(tag,weight) VALUES(?,?)
                   ON CONFLICT(tag) DO UPDATE SET weight=tag_profile.weight+excluded.weight""",
                (tag, weight),
            )
        self.connection.commit()

    def recommendations(self, limit=20):
        profile = dict(self.connection.execute("SELECT tag,weight FROM tag_profile"))
        rows = self.connection.execute(
            "SELECT uri,title,source,tags,score,views,last_seen FROM candidates LIMIT 200"
        ).fetchall()
        scored = []
        for uri, title, source, tags_text, score, views, last_seen in rows:
            tags = tags_text.split()
            affinity = sum(profile.get(tag, 0.0) for tag in tags)
            freshness = min(1.0, max(0.0, (time.time() - last_seen) / 604800))
            total = score * 0.5 + affinity * 0.3 + freshness * 0.2 - views * 0.05
            scored.append((total, uri, title, source, tags))
        scored.sort(reverse=True)
        result, selected_uris = [], set()
        best_by_source = {}
        for item in scored:
            best_by_source.setdefault(item[3], item)
        source_leaders = sorted(
            best_by_source.values(),
            key=lambda item: SOURCE_PRIORITY.get(item[3], 99),
        )
        for item in source_leaders:
            result.append(item)
            selected_uris.add(item[1])
            if len(result) == limit:
                return result

        category_counts = {}
        for item in scored:
            if item[1] in selected_uris:
                continue
            category = item[4][0] if item[4] else item[3]
            if category_counts.get(category, 0) >= 3:
                continue
            result.append(item)
            category_counts[category] = category_counts.get(category, 0) + 1
            if len(result) == limit:
                break
        return result


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


def load_config():
    try:
        config = {**DEFAULT_CONFIG, **json.loads(CONFIG_FILE.read_text(encoding="utf-8"))}
    except (OSError, json.JSONDecodeError):
        config = dict(DEFAULT_CONFIG)
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
    def __init__(self, title, source, tags, score, thumbnail, open_callback, favorite_callback):
        super().__init__()
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                          css_classes=["suggestion-card"])
        picture = Gtk.Picture.new_for_filename(str(thumbnail)) if thumbnail.exists() else Gtk.Picture()
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.set_size_request(250, 150)
        content.append(picture)
        content.append(Gtk.Label(label=title, xalign=0, wrap=True, lines=2,
                                 ellipsize=3, css_classes=["card-title"]))
        content.append(Gtk.Label(label=source, xalign=0, ellipsize=3,
                                 css_classes=["suggestion-source"]))
        details = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        stars = max(3, min(5, int(round(3 + score))))
        details.append(Gtk.Label(label="★" * stars + "☆" * (5 - stars), xalign=0,
                                 hexpand=True, css_classes=["suggestion-rating"]))
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
        self.selected = Path(self.config["wallpaper"]) if self.config["wallpaper"] else None
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
        self.views.connect("notify::visible-child-name", self.view_changed)
        switcher = Gtk.StackSwitcher(stack=self.views)
        header.set_title_widget(switcher)
        toolbar.set_content(self.views)
        self.set_content(toolbar)

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
        page.append(navigation)

        self.web_view = WebKit.WebView()
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
            label="Les suggestions évoluent avec vos visites, téléchargements et fonds appliqués.",
            xalign=0, wrap=True, css_classes=["dim-label"],
        )
        page.append(self.suggestion_hint)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        self.suggestion_flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                                           column_spacing=14, row_spacing=14,
                                           min_children_per_line=2, max_children_per_line=4)
        self.suggestion_flow.set_valign(Gtk.Align.START)
        scroll.set_child(self.suggestion_flow)
        page.append(scroll)
        return page

    def view_changed(self, stack, _property):
        if stack.get_visible_child_name() == "suggestions":
            self.refresh_suggestions()

    def refresh_suggestions(self):
        while child := self.suggestion_flow.get_first_child():
            self.suggestion_flow.remove(child)
        recommendations = self.taste.recommendations()
        if not recommendations:
            self.suggestion_hint.set_text(
                "Parcourez quelques fonds dans Découvrir pour initialiser vos suggestions."
            )
            return
        self.suggestion_hint.set_text(
            f"{len(recommendations)} résultats classés localement et diversifiés par style."
        )
        missing = []
        for score, uri, title, source, tags in recommendations:
            thumbnail = suggestion_thumbnail_path(uri)
            card = SuggestionCard(
                title, source, tags, score, thumbnail,
                lambda _button, target=uri: self.open_suggestion(_button, target),
                lambda _button, label=title: self.favorite_suggestion(label),
            )
            self.suggestion_flow.append(card)
            if not thumbnail.exists() and uri not in self.suggestion_thumbnail_attempted:
                self.suggestion_thumbnail_attempted.add(uri)
                missing.append((uri, thumbnail))
        if missing:
            threading.Thread(target=self.generate_suggestion_thumbnails,
                             args=(missing,), daemon=True).start()

    def generate_suggestion_thumbnails(self, items):
        changed = False
        for uri, destination in items:
            changed = fetch_suggestion_thumbnail(uri, destination) or changed
        if changed:
            GLib.idle_add(self.refresh_suggestions)

    def favorite_suggestion(self, title):
        self.taste.reinforce(title, 4.0)
        self.refresh_suggestions()

    def open_suggestion(self, _button, uri):
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
            result = subprocess.run(
                [
                    "yt-dlp", "--no-playlist", "--no-progress",
                    "--print", "after_move:filepath",
                    "-o", str(LIBRARY_DIR / f"{title[:160]}.%(ext)s"), download_uri,
                ],
                capture_output=True, text=True, check=False,
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
        METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = METADATA_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.metadata, indent=2) + "\n", encoding="utf-8")
        temporary.replace(METADATA_FILE)

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
                subprocess.run(["ffmpegthumbnailer", "-i", str(video), "-o", str(thumb), "-s", "480", "-t", "20"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
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
        return {
            "wallpaper": str(self.selected) if self.selected else "",
            "output": self.output_names[self.output.get_selected()],
            "volume": int(self.volume.get_value()),
            "speed": self.speeds[self.speed.get_selected()],
            "loop": self.loop[1].get_active(),
            "hardware_decode": self.hardware[1].get_active(),
            "auto_pause": self.auto_pause[1].get_active(),
            "autostart": self.autostart[1].get_active(),
        }

    def run_controller(self, action, callback=None):
        def worker():
            result = subprocess.run([str(CONTROLLER), action], capture_output=True, text=True, check=False)
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
            extract = subprocess.run(
                ["ffmpegthumbnailer", "-i", str(self.selected), "-o", str(output),
                 "-s", "1920", "-t", "20"],
                capture_output=True, text=True, check=False,
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
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

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


if __name__ == "__main__":
    raise SystemExit(MPVpaperApplication().run())
