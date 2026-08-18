#!/usr/bin/env python3

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk


APP_ID = "io.github.kebemouhamet08.MPVpaperEngine"
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"}
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "mpvpaper-engine"
CONFIG_FILE = CONFIG_DIR / "config.json"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "mpvpaper-engine" / "thumbnails"
METADATA_FILE = CACHE_DIR.parent / "metadata.json"
LIBRARY_DIR = Path.home() / "Pictures" / "Wallpapers" / "Live"
LEGACY_LIBRARY_DIR = Path.home() / "Pictures" / "wallpapers"
CONTROLLER = Path.home() / ".local" / "lib" / "mpvpaper-engine" / "mpvpaper-enginectl.py"
SDDM_INSTALLER = Path.home() / ".local" / "lib" / "mpvpaper-engine" / "install-sddm-background.sh"
DEFAULT_CONFIG = {
    "wallpaper": "", "output": "*", "volume": 0, "speed": 1.0,
    "loop": True, "hardware_decode": True, "auto_pause": True, "autostart": True,
}


def load_config():
    try:
        return {**DEFAULT_CONFIG, **json.loads(CONFIG_FILE.read_text(encoding="utf-8"))}
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)


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


class MPVpaperWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="MPVpaper Engine")
        self.set_default_size(1120, 720)
        self.set_size_request(760, 520)
        self.config = load_config()
        self.metadata = self.load_metadata()
        self.selected = Path(self.config["wallpaper"]) if self.config["wallpaper"] else None
        self.cards = []
        LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.build_ui()
        self.load_library()
        self.refresh_status()

    def build_ui(self):
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        title = Adw.WindowTitle(title="MPVpaper Engine", subtitle="Fonds vidéo pour Hyprland")
        header.set_title_widget(title)
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
        toolbar.set_content(paned)
        self.set_content(toolbar)

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
        self.config = self.current_config()
        save_config(self.config)
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
                    ["pkexec", str(SDDM_INSTALLER), str(output)],
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
            self.status.set_text(result.stderr.strip() or "Installation du fond de connexion annulée")

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
        self.status.set_text("Service actif" if result.stdout.strip() == "active" else "Aucun fond vidéo actif")


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
            picture { border-radius: 4px; background: #090a0d; }
        """)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        window = self.props.active_window or MPVpaperWindow(self)
        window.present()


if __name__ == "__main__":
    raise SystemExit(MPVpaperApplication().run())
