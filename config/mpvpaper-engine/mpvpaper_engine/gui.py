"""GTK4/libadwaita application for MPVpaper Engine 2."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, WebKit

from .cache import CacheManager
from .gui_backend import GuiBackend
from .models import Wallpaper
from .recommendations import Recommendation


APP_ID = "io.github.kebemouhamet08.MPVpaperEngine.V2"
DOWNLOAD_QUALITIES = (
    ("Auto", 0), ("1080p", 1080), ("1440p", 1440),
    ("4K", 2160), ("8K", 4320),
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
PAGES = (
    ("library", "Bibliothèque", "folder-pictures-symbolic"),
    ("discover", "Découvrir", "system-search-symbolic"),
    ("favorites", "Favoris", "emblem-favorite-symbolic"),
    ("playlists", "Playlists", "view-list-symbolic"),
    ("recent", "Récents", "document-open-recent-symbolic"),
    ("monitors", "Écrans", "video-display-symbolic"),
    ("settings", "Réglages", "preferences-system-symbolic"),
)

STYLE = """
window.engine-window { background: #101116; color: #f5f6f8; }
window.engine-window headerbar { background: #17191f; color: #f5f6f8; box-shadow: none; }
window.engine-window label { color: #f5f6f8; }
window.engine-window .dim-label { color: #aeb3bf; }
window.engine-window entry,
window.engine-window searchentry,
window.engine-window dropdown { background: #252831; color: #f5f6f8; }
.app-sidebar { background: #14161c; border-right: 1px solid #2b2f39; }
.navigation-sidebar { background: transparent; }
.navigation-sidebar row { margin: 3px 2px; padding: 2px; border-radius: 8px; }
.navigation-sidebar row:hover { background: #20232b; }
.navigation-sidebar row:selected { background: #34232b; }
.navigation-sidebar row:selected image { color: #ff5b80; }
.page-title { font-weight: 800; }
.library-count { padding: 5px 10px; border-radius: 99px; background: #20232b; }
.wallpaper-grid { background: transparent; }
.wallpaper-card-child { padding: 0; border-radius: 9px; }
.wallpaper-card {
  padding: 8px; border-radius: 9px; background: #1b1e25;
  border: 1px solid #30343e;
}
.wallpaper-card:hover { background: #242832; border-color: #e23864; }
.recommendation-card { padding: 9px; border-radius: 9px; background: #1b1e25;
  border: 1px solid #30343e; }
.recommendation-card:hover { border-color: #ff5277; }
.discover-toolbar { padding: 8px; border-radius: 9px; background: #1b1e25; }
.source-picker { padding: 5px; border-radius: 9px; background: #17191f; }
.ai-badge { padding: 5px 9px; border-radius: 99px; background: #3b202a; color: #ff7896; }
.wallpaper-thumbnail { background: #090a0d; border-radius: 6px; }
.card-details { font-size: 0.88em; }
.inspector-pane { background: #17191f; border-left: 1px solid #30343e; }
.inspector-preview { background: #090a0d; border-radius: 8px; border: 1px solid #30343e; }
.inspector-section { padding: 10px; border-radius: 8px; background: #1d2027; }
button.suggested-action { background: #ff5277; color: #19080d; font-weight: 700; }
button.suggested-action:hover { background: #ff6f8e; }
button { border-radius: 7px; transition: background-color 180ms ease, color 180ms ease; }
button.success-download { background: #35c98a; color: #071c13; font-weight: 800; }
button.success-like { background: #ff5277; color: #240811; font-weight: 800; }
scale highlight { background: #ff5277; }
switch:checked { background: #ff5277; }
"""


class AsyncTasks:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="mpvpaper-gui")

    def run(self, operation, success, failure):
        future = self.pool.submit(operation)

        def completed(done):
            try:
                result = done.result()
            except Exception as error:  # UI boundary: show the useful message.
                GLib.idle_add(failure, error)
            else:
                GLib.idle_add(success, result)

        future.add_done_callback(completed)

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)


def _details(item: Wallpaper) -> str:
    resolution = f"{item.width}×{item.height}" if item.width and item.height else "résolution inconnue"
    fps = f" · {item.fps:g} FPS" if item.fps else ""
    duration = f" · {int(item.duration // 60)}:{int(item.duration % 60):02d}" if item.duration else ""
    return f"{resolution}{fps}{duration}"


class WallpaperCard(Gtk.FlowBoxChild):
    def __init__(self, item: Wallpaper, selected, activated, context):
        super().__init__()
        self.item = item
        self.set_size_request(220, -1)
        self.set_hexpand(True)
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.START)
        self.add_css_class("wallpaper-card-child")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7,
                      hexpand=True, css_classes=["wallpaper-card"])
        picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True,
                              hexpand=True, vexpand=True)
        preview = item.thumbnail_path if item.thumbnail_path and item.thumbnail_path.is_file() else (
            item.path if item.media_type.value == "image" else None
        )
        if preview:
            picture.set_filename(str(preview))
        picture.add_css_class("wallpaper-thumbnail")
        frame = Gtk.AspectFrame(ratio=16 / 9, obey_child=False,
                                hexpand=True, child=picture)
        frame.set_size_request(210, 118)
        frame.add_css_class("wallpaper-frame")
        box.append(frame)
        title = ("★ " if item.favorite else "") + item.title
        box.append(Gtk.Label(label=title, xalign=0, ellipsize=3, max_width_chars=28,
                             css_classes=["heading"]))
        box.append(Gtk.Label(label=_details(item), xalign=0, ellipsize=3,
                             css_classes=["dim-label", "card-details"]))
        self.set_child(box)
        click = Gtk.GestureClick(button=0)
        click.connect("pressed", self._pressed, selected, activated, context)
        self.add_controller(click)

    def _pressed(self, gesture, count, x, y, selected, activated, context):
        button = gesture.get_current_button()
        if button == 3:
            context(self, x, y)
        elif count == 2:
            activated(self.item)
        else:
            selected(self.item)


class RecommendationCard(Gtk.FlowBoxChild):
    def __init__(self, item: Recommendation, opened, feedback, downloaded):
        super().__init__()
        self.set_size_request(235, -1)
        self.set_hexpand(True)
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.START)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7,
                      hexpand=True, css_classes=["recommendation-card"])
        picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True,
                              hexpand=True, vexpand=True,
                              css_classes=["wallpaper-thumbnail"])
        if item.thumbnail.is_file():
            picture.set_filename(str(item.thumbnail))
        frame = Gtk.AspectFrame(ratio=16 / 9, obey_child=False, child=picture,
                                hexpand=True)
        frame.set_size_request(220, 124)
        box.append(frame)
        box.append(Gtk.Label(label=item.title, xalign=0, ellipsize=3,
                             max_width_chars=34, css_classes=["heading"]))
        tags = " · ".join(item.tags[:4]) or "sans catégorie"
        box.append(Gtk.Label(
            label=f"{item.source}  •  {item.rating:.1f}/5\n{tags}", xalign=0,
            ellipsize=3, max_width_chars=38,
            css_classes=["dim-label", "card-details"],
        ))
        actions = Gtk.Box(spacing=6, homogeneous=True)
        open_button = Gtk.Button(label="Voir", hexpand=True,
                                 css_classes=["suggested-action"])
        open_button.connect("clicked", lambda _button: opened(item.uri))
        download = Gtk.Button(label="↓ Télécharger",
                              tooltip_text="Ajouter à la bibliothèque")
        download.connect("clicked", lambda button: downloaded(item, button))
        dislike = Gtk.Button(label="Moins",
                             tooltip_text="Moins de fonds comme celui-ci")
        dislike.connect("clicked", lambda button: feedback(item.uri, -1, button))
        like = Gtk.Button(label="♥ Aimer",
                          tooltip_text="Aimer et adapter les suggestions")
        like.connect("clicked", lambda button: feedback(item.uri, 1, button))
        actions.append(open_button)
        actions.append(download)
        actions.append(dislike)
        actions.append(like)
        box.append(actions)
        self.set_child(box)


class EngineWindow(Adw.ApplicationWindow):
    def __init__(self, app, backend=None):
        super().__init__(application=app, title="MPVpaper Engine 2")
        self.backend = backend or GuiBackend()
        self.tasks = AsyncTasks()
        self.selected: Wallpaper | None = None
        self.cards: list[WallpaperCard] = []
        self.thumbnail_requests: set[int] = set()
        self.last_failed_download = None
        self.output_names = ["*"]
        self.set_default_size(1280, 760)
        self.set_size_request(900, 580)
        self.add_css_class("engine-window")
        self.connect("close-request", self._close)
        self._build()
        self.reload(scan=True)
        self.refresh_outputs()

    @staticmethod
    def _button_busy(button, text):
        content = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        spinner = Gtk.Spinner(spinning=True)
        content.append(spinner)
        content.append(Gtk.Label(label=text))
        button.set_child(content)
        button.set_sensitive(False)

    @staticmethod
    def _restore_label(button, text):
        button.set_child(None)
        button.set_label(text)
        button.set_sensitive(True)

    def _success_animation(self, button, text, css_class, restore, after=None):
        button.set_child(None)
        button.set_label(text)
        button.set_sensitive(True)
        button.add_css_class(css_class)
        state = {"step": 0}

        def pulse():
            state["step"] += 1
            if state["step"] >= 6:
                button.remove_css_class(css_class)
                restore()
                if after is not None:
                    after()
                return False
            if state["step"] % 2:
                button.remove_css_class(css_class)
            else:
                button.add_css_class(css_class)
            return True

        GLib.timeout_add(180, pulse)

    def _build(self):
        self.pages = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.library_flow = self._grid_page("library", "Votre bibliothèque")
        self.favorite_flow = self._grid_page("favorites", "Vos favoris")
        self.pages.add_named(self._discover_page(), "discover")
        self.pages.add_named(self._playlists_page(), "playlists")
        self.pages.add_named(self._recent_page(), "recent")
        self.pages.add_named(self._monitors_page(), "monitors")
        self.pages.add_named(self._settings_page(), "settings")

        content_toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.search = Gtk.SearchEntry(placeholder_text="Rechercher")
        self.search.set_size_request(340, -1)
        self.search.connect("search-changed", lambda _entry: self.reload(scan=False))
        header.set_title_widget(self.search)
        self.media_filter = Gtk.DropDown.new_from_strings(
            ["Tous les médias", "Vidéos", "Images"]
        )
        self.media_filter.set_tooltip_text("Séparer les vidéos et les images")
        self.media_filter.connect("notify::selected", lambda *_args: self.reload(scan=False))
        header.pack_start(self.media_filter)
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Actualiser")
        refresh.connect("clicked", lambda _button: self.reload(scan=True))
        header.pack_end(refresh)
        content_toolbar.add_top_bar(header)
        content_toolbar.set_content(self.pages)

        overlay = Adw.OverlaySplitView()
        overlay.set_content(content_toolbar)
        overlay.set_sidebar(self._inspector())
        overlay.set_sidebar_position(Gtk.PackType.END)
        overlay.set_min_sidebar_width(300)
        overlay.set_max_sidebar_width(390)
        overlay.set_show_sidebar(True)
        self.inspector_split = overlay

        sidebar_page = Adw.NavigationPage(title="Navigation", child=self._sidebar())
        content_page = Adw.NavigationPage(title="Bibliothèque", child=overlay)
        split = Adw.NavigationSplitView(sidebar=sidebar_page, content=content_page)
        split.set_min_sidebar_width(190)
        split.set_max_sidebar_width(240)
        self.set_content(split)

    def _sidebar(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                      margin_top=12, margin_bottom=12, margin_start=8, margin_end=8)
        box.add_css_class("app-sidebar")
        title = Gtk.Label(label="MPVpaper Engine", xalign=0, margin_start=8,
                          css_classes=["title-2"])
        box.append(title)
        navigation = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE,
                                 css_classes=["navigation-sidebar"])
        for name, label, icon in PAGES:
            row = Adw.ActionRow(title=label, activatable=True)
            row.page_name = name
            row.add_prefix(Gtk.Image(icon_name=icon))
            navigation.append(row)
            if name == "library":
                navigation.select_row(row)
        navigation.connect("row-selected", self._page_selected)
        box.append(navigation)
        return box

    def _grid_page(self, name, title):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                        margin_top=22, margin_bottom=22, margin_start=24, margin_end=24)
        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        heading.append(Gtk.Label(label=title, xalign=0, hexpand=True,
                                 css_classes=["title-1", "page-title"]))
        count = Gtk.Label(label="", css_classes=["dim-label", "library-count"])
        heading.append(count)
        outer.append(heading)
        if name == "library":
            self.library_count = count
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                           column_spacing=14, row_spacing=16, min_children_per_line=2,
                           max_children_per_line=3, valign=Gtk.Align.START,
                           halign=Gtk.Align.FILL, hexpand=True)
        flow.add_css_class("wallpaper-grid")
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True, child=flow,
                                    hscrollbar_policy=Gtk.PolicyType.NEVER,
                                    vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
        outer.append(scroll)
        self.pages.add_named(outer, name)
        return flow

    def _discover_page(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                        margin_top=16, margin_bottom=16,
                        margin_start=18, margin_end=18)
        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        heading.append(Gtk.Label(label="Découvrir", xalign=0, hexpand=True,
                                 css_classes=["title-1", "page-title"]))
        self.discover_stack = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.CROSSFADE,
            vexpand=True, hexpand=True,
        )
        switcher = Gtk.StackSwitcher(stack=self.discover_stack)
        heading.append(switcher)
        outer.append(heading)
        self.discover_stack.add_titled(
            self._browser_page(), "browser", "Navigateur intégré"
        )
        self.discover_stack.add_titled(
            self._suggestions_page(), "suggestions", "Suggestions IA"
        )
        outer.append(self.discover_stack)
        return outer

    def _browser_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        toolbar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                          css_classes=["discover-toolbar"])
        actions = Gtk.Box(spacing=6)
        back = Gtk.Button(icon_name="go-previous-symbolic", tooltip_text="Précédent")
        forward = Gtk.Button(icon_name="go-next-symbolic", tooltip_text="Suivant")
        reload_button = Gtk.Button(icon_name="view-refresh-symbolic",
                                   tooltip_text="Recharger")
        back.connect("clicked", lambda _button: self.discover_web.go_back()
                     if self.discover_web.can_go_back() else None)
        forward.connect("clicked", lambda _button: self.discover_web.go_forward()
                        if self.discover_web.can_go_forward() else None)
        reload_button.connect("clicked", lambda _button: self.discover_web.reload())
        actions.append(back)
        actions.append(forward)
        actions.append(reload_button)
        self.discover_sources = (
            ("Steam Workshop", "https://steamcommunity.com/workshop/browse?appid=431960"),
            ("MoeWalls", "https://moewalls.com/"),
            ("MotionBGS", "https://motionbgs.com/"),
            ("YouTube Live 4K", "https://www.youtube.com/results?search_query=live+wallpaper+4k"),
        )
        source = Gtk.DropDown.new_from_strings([name for name, _uri in self.discover_sources])
        source.set_tooltip_text("Sources populaires")
        source.connect("notify::selected", self._browser_source_changed)
        actions.append(source)
        self.download_quality = Gtk.DropDown.new_from_strings(
            [label for label, _height in DOWNLOAD_QUALITIES]
        )
        self.download_quality.set_tooltip_text("Qualité du téléchargement")
        actions.append(self.download_quality)
        self.download_button = Gtk.Button(
            icon_name="document-save-symbolic",
            tooltip_text="Télécharger dans la bibliothèque",
        )
        self.download_button.connect("clicked", self._download_current_page)
        actions.append(self.download_button)
        like = Gtk.Button(icon_name="emblem-favorite-symbolic",
                          tooltip_text="Aimer et améliorer les suggestions")
        like.connect("clicked", self._like_current_page)
        actions.append(like)
        self.adblock_button = Gtk.ToggleButton(
            icon_name="security-high-symbolic", active=True,
            tooltip_text="Blocage des publicités actif",
        )
        self.adblock_button.connect("toggled", self._adblock_toggled)
        actions.append(self.adblock_button)
        toolbar.append(actions)
        address_row = Gtk.Box(spacing=6)
        self.discover_address = Gtk.Entry(
            placeholder_text="Adresse ou recherche…", hexpand=True
        )
        self.discover_address.connect("activate", self._browser_address_activated)
        address_row.append(self.discover_address)
        firefox = Gtk.Button(label="Ouvrir dans Firefox",
                             icon_name="web-browser-symbolic")
        firefox.connect("clicked", self._open_in_firefox)
        address_row.append(firefox)
        toolbar.append(address_row)
        box.append(toolbar)
        self.web_content = WebKit.UserContentManager()
        self.adblock_style = WebKit.UserStyleSheet.new(
            ADBLOCK_CSS, WebKit.UserContentInjectedFrames.ALL_FRAMES,
            WebKit.UserStyleLevel.USER, None, None,
        )
        self.web_content.add_style_sheet(self.adblock_style)
        self.adblock_filter = None
        self.discover_web = WebKit.WebView(
            user_content_manager=self.web_content, vexpand=True, hexpand=True
        )
        self.discover_web.connect("notify::uri", self._browser_uri_changed)
        self.discover_web.connect("load-changed", self._browser_load_changed)
        self.discover_web.connect("decide-policy", self._browser_decide_policy)
        self.discover_web.load_uri(self.discover_sources[0][1])
        box.append(self.discover_web)
        status_row = Gtk.Box(spacing=8)
        self.browser_status = Gtk.Label(
            label="Navigateur isolé dans MPVpaper Engine · téléchargements contrôlés par le site",
            xalign=0, ellipsize=3, hexpand=True, css_classes=["dim-label"],
        )
        status_row.append(self.browser_status)
        self.browser_firefox_retry = Gtk.Button(
            label="Réessayer avec Firefox", visible=False,
            tooltip_text="Utiliser temporairement la session Firefox pour cette vidéo",
        )
        self.browser_firefox_retry.connect(
            "clicked", self._retry_download_with_firefox
        )
        status_row.append(self.browser_firefox_retry)
        box.append(status_row)
        self._compile_adblock_filter()
        self.tasks.run(self.backend.discovery_download_profile,
                       self._download_profile_ready, lambda _error: False)
        return box

    def _suggestions_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        description = Gtk.Box(spacing=10)
        description.append(Gtk.Label(label="IA locale", css_classes=["ai-badge"]))
        description.append(Gtk.Label(
            label="Classe les fonds selon leur popularité, vos goûts et plusieurs sources.",
            xalign=0, wrap=True, hexpand=True, css_classes=["dim-label"],
        ))
        box.append(description)
        controls = Gtk.Box(spacing=10, css_classes=["discover-toolbar"])
        controls.append(Gtk.Label(label="Nombre", css_classes=["heading"]))
        adjustment = Gtk.Adjustment(value=16, lower=4, upper=60,
                                    step_increment=1, page_increment=4)
        self.suggestion_count = Gtk.SpinButton(adjustment=adjustment, numeric=True)
        self.suggestion_count.set_width_chars(3)
        controls.append(self.suggestion_count)
        controls.append(Gtk.Label(label="Qualité", css_classes=["heading"]))
        self.suggestion_download_quality = Gtk.DropDown.new_from_strings(
            [label for label, _height in DOWNLOAD_QUALITIES]
        )
        self.suggestion_download_quality.set_tooltip_text(
            "Qualité utilisée par les boutons Télécharger"
        )
        controls.append(self.suggestion_download_quality)
        self.suggestion_adblock = Gtk.ToggleButton(
            label="🛡 Adblock", active=self.adblock_button.get_active(),
            tooltip_text="Protection du navigateur intégré",
        )
        self.suggestion_adblock.connect(
            "toggled", self._suggestion_adblock_toggled
        )
        controls.append(self.suggestion_adblock)
        refresh = Gtk.Button(label="Mettre à jour", icon_name="view-refresh-symbolic",
                             css_classes=["suggested-action"])
        refresh.connect("clicked", self._save_and_load_recommendations)
        controls.append(refresh)
        self.suggestion_status = Gtk.Label(label="", xalign=0, hexpand=True,
                                           ellipsize=3, css_classes=["dim-label"])
        controls.append(self.suggestion_status)
        self.suggestion_firefox_retry = Gtk.Button(
            label="Réessayer avec Firefox", visible=False,
            tooltip_text="Utiliser temporairement la session Firefox",
        )
        self.suggestion_firefox_retry.connect(
            "clicked", self._retry_download_with_firefox
        )
        controls.append(self.suggestion_firefox_retry)
        box.append(controls)
        box.append(Gtk.Label(label="Sources utilisées", xalign=0,
                             css_classes=["heading"]))
        self.source_controls = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
            column_spacing=8, row_spacing=6, min_children_per_line=1,
            max_children_per_line=5, css_classes=["source-picker"],
        )
        box.append(self.source_controls)
        self.suggestion_flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
            column_spacing=14, row_spacing=14, min_children_per_line=2,
            max_children_per_line=4, valign=Gtk.Align.START,
            halign=Gtk.Align.FILL, hexpand=True,
        )
        scroll = Gtk.ScrolledWindow(
            child=self.suggestion_flow, vexpand=True, hexpand=True,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
        )
        box.append(scroll)
        self.recommendations_loaded = False
        self.recommendations_loading = False
        self.recommendation_sources = {}
        return box

    def _browser_source_changed(self, dropdown, _param):
        index = dropdown.get_selected()
        if index < len(self.discover_sources):
            self.discover_web.load_uri(self.discover_sources[index][1])

    def _browser_address_activated(self, entry):
        value = entry.get_text().strip()
        if not value:
            return
        if "://" not in value:
            value = "https://www.google.com/search?q=" + GLib.uri_escape_string(value, None, True)
        self.discover_web.load_uri(value)

    def _browser_uri_changed(self, webview, _param):
        self.discover_address.set_text(webview.get_uri() or "")

    def _browser_load_changed(self, webview, event):
        if event == WebKit.LoadEvent.FINISHED:
            self.browser_status.set_text(webview.get_title() or "Page chargée")

    def _browser_decide_policy(self, _webview, decision, decision_type):
        if decision_type != WebKit.PolicyDecisionType.NEW_WINDOW_ACTION:
            return False
        action = decision.get_navigation_action()
        if action.is_user_gesture():
            self.discover_web.load_uri(action.get_request().get_uri())
        decision.ignore()
        return True

    def _compile_adblock_filter(self):
        rules = [{
            "trigger": {"url-filter": f".*{domain.replace('.', r'\.') }.*"},
            "action": {"type": "block"},
        } for domain in AD_DOMAINS]
        try:
            directory = self.backend.paths.cache_home / "adblock"
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.adblock_store = WebKit.UserContentFilterStore.new(str(directory))
            self.adblock_store.save(
                "mpvpaper-engine-ads",
                GLib.Bytes.new(json.dumps(rules).encode()),
                None, self._adblock_filter_ready,
            )
        except (OSError, GLib.Error) as error:
            self.browser_status.set_text(f"Bloqueur réseau indisponible : {error}")

    def _adblock_filter_ready(self, store, result):
        try:
            self.adblock_filter = store.save_finish(result)
        except GLib.Error as error:
            self.browser_status.set_text(
                f"Bloqueur réseau indisponible : {error.message}"
            )
            return
        if self.adblock_button.get_active():
            self.web_content.add_filter(self.adblock_filter)
            self.discover_web.reload()

    def _adblock_toggled(self, button):
        self.web_content.remove_all_filters()
        self.web_content.remove_all_style_sheets()
        if button.get_active():
            self.web_content.add_style_sheet(self.adblock_style)
            if self.adblock_filter is not None:
                self.web_content.add_filter(self.adblock_filter)
            button.set_tooltip_text("Blocage des publicités actif")
            self.browser_status.set_text("Publicités et fenêtres intrusives bloquées")
        else:
            button.set_tooltip_text("Blocage des publicités désactivé")
            self.browser_status.set_text("Blocage des publicités désactivé")
        if (hasattr(self, "suggestion_adblock")
                and self.suggestion_adblock.get_active() != button.get_active()):
            self.suggestion_adblock.handler_block_by_func(
                self._suggestion_adblock_toggled
            )
            self.suggestion_adblock.set_active(button.get_active())
            self.suggestion_adblock.handler_unblock_by_func(
                self._suggestion_adblock_toggled
            )
        self.discover_web.reload()

    def _suggestion_adblock_toggled(self, button):
        if self.adblock_button.get_active() != button.get_active():
            self.adblock_button.set_active(button.get_active())
        state = "actif" if button.get_active() else "désactivé"
        self.suggestion_status.set_text(f"Adblock {state} dans le navigateur intégré")

    def _download_profile_ready(self, profile):
        self.download_quality.set_tooltip_text(
            f"Auto : {profile.target_height}p · {profile.reason}"
        )
        return False

    def _download_current_page(self, _button):
        uri = self.discover_web.get_uri()
        if not uri:
            return
        title = self.discover_web.get_title() or "wallpaper"
        height = DOWNLOAD_QUALITIES[self.download_quality.get_selected()][1]
        target = "automatique" if height == 0 else f"{height}p"
        self.pending_download = (uri, title, height, "browser")
        self.browser_firefox_retry.set_visible(False)
        self._button_busy(self.download_button, "Téléchargement…")
        self.browser_status.set_text(f"Téléchargement en cours · qualité {target}…")
        self.tasks.run(
            lambda: self.backend.download_discovery_page(uri, title, height),
            self._download_finished, self._download_failed,
        )

    def _download_finished(self, outcome):
        if outcome.path is None:
            self.download_button.set_child(None)
            self.download_button.set_icon_name("document-save-symbolic")
            self.download_button.set_sensitive(True)
            self.browser_status.set_text(f"Téléchargement impossible : {outcome.message}")
            if outcome.source == "authentication-required":
                self.last_failed_download = self.pending_download
                self.browser_firefox_retry.set_visible(True)
        else:
            self.browser_firefox_retry.set_visible(False)
            self.browser_status.set_text(
                f"Ajouté à la bibliothèque : {outcome.path.name}"
            )
            self._success_animation(
                self.download_button, "✓ Téléchargé", "success-download",
                lambda: self.download_button.set_icon_name("document-save-symbolic"),
            )
            self.reload(scan=False)
        return False

    def _download_failed(self, error):
        self.download_button.set_child(None)
        self.download_button.set_icon_name("document-save-symbolic")
        self.download_button.set_sensitive(True)
        self.browser_status.set_text(f"Téléchargement impossible : {error}")
        return False

    def _retry_download_with_firefox(self, button):
        if self.last_failed_download is None:
            return
        uri, title, height, scope = self.last_failed_download
        self._button_busy(button, "Session Firefox…")
        status = (self.browser_status if scope == "browser"
                  else self.suggestion_status)
        status.set_text("Nouvel essai avec la session Firefox…")

        def finished(outcome):
            self._restore_label(button, "Réessayer avec Firefox")
            if outcome.path is None:
                status.set_text(f"Échec avec Firefox : {outcome.message}")
                button.set_visible(True)
            else:
                status.set_text(f"Ajouté à la bibliothèque : {outcome.path.name}")
                self._success_animation(
                    button, "✓ Téléchargé", "success-download",
                    lambda: self._restore_label(button, "Réessayer avec Firefox"),
                    after=lambda: button.set_visible(False),
                )
                self.last_failed_download = None
                self.reload(scan=False)
            return False

        def failed(error):
            self._restore_label(button, "Réessayer avec Firefox")
            status.set_text(f"Échec avec Firefox : {error}")
            return False

        self.tasks.run(
            lambda: self.backend.download_discovery_page(
                uri, title, height, firefox=True
            ),
            finished, failed,
        )

    def _like_current_page(self, button):
        uri = self.discover_web.get_uri()
        if not uri:
            return
        title = self.discover_web.get_title() or uri
        self._button_busy(button, "Enregistrement…")
        self.browser_status.set_text("Préférence enregistrée…")

        def done(_result):
            self.recommendations_loaded = False
            self.browser_status.set_text("Aimé ♥ · les suggestions ont été adaptées")
            self._success_animation(
                button, "♥ Aimé ✓", "success-like",
                lambda: button.set_icon_name("emblem-favorite-symbolic"),
            )
            return False

        def failed(error):
            button.set_child(None)
            button.set_icon_name("emblem-favorite-symbolic")
            button.set_sensitive(True)
            self.browser_status.set_text(f"Impossible d’aimer cette page : {error}")
            return False

        self.tasks.run(
            lambda: self.backend.like_discovery_page(uri, title), done, failed
        )

    def _open_in_firefox(self, _button):
        uri = self.discover_web.get_uri() or self.discover_sources[0][1]
        try:
            if GLib.find_program_in_path("firefox"):
                Gio.Subprocess.new(["firefox", uri], Gio.SubprocessFlags.NONE)
                self.browser_status.set_text("Page envoyée à Firefox")
            else:
                Gio.AppInfo.launch_default_for_uri(uri, None)
                self.browser_status.set_text("Firefox absent : navigateur par défaut utilisé")
        except GLib.Error as error:
            self.browser_status.set_text(f"Ouverture impossible : {error.message}")

    def _load_recommendations(self):
        if self.recommendations_loading:
            return
        self.recommendations_loading = True
        self.suggestion_status.set_text("Analyse locale des suggestions…")
        self.tasks.run(
            self.backend.recommendation_data,
            self._recommendations_ready,
            self._recommendations_failed,
        )

    def _save_and_load_recommendations(self, _button=None):
        enabled = [source for source, control in self.recommendation_sources.items()
                   if control.get_active()]
        limit = self.suggestion_count.get_value_as_int()
        self.recommendations_loading = True
        self.suggestion_status.set_text("Préférences enregistrées…")

        def update():
            self.backend.configure_recommendations(
                enabled_sources=enabled, limit=limit
            )
            return self.backend.recommendation_data()

        self.tasks.run(update, self._recommendations_ready,
                       self._recommendations_failed)

    def _recommendations_ready(self, data):
        self.recommendations_loading = False
        self.recommendations_loaded = True
        settings = data["settings"]
        self.suggestion_count.set_value(settings["limit"])
        while child := self.source_controls.get_first_child():
            self.source_controls.remove(child)
        self.recommendation_sources = {}
        for source, count in data["sources"].items():
            control = Gtk.CheckButton(label=f"{source} ({count})")
            control.set_active(source in settings["enabled_sources"])
            self.source_controls.append(control)
            self.recommendation_sources[source] = control
        while child := self.suggestion_flow.get_first_child():
            self.suggestion_flow.remove(child)
        for item in data["items"]:
            self.suggestion_flow.append(RecommendationCard(
                item, self._open_recommendation, self._recommendation_feedback,
                self._download_recommendation,
            ))
        active_count = len(settings["enabled_sources"])
        self.suggestion_status.set_text(
            f"{len(data['items'])} résultats · {active_count} source(s) active(s)"
        )
        return False

    def _recommendations_failed(self, error):
        self.recommendations_loading = False
        self.suggestion_status.set_text(f"Suggestions indisponibles : {error}")
        return False

    def _open_recommendation(self, uri):
        self.discover_stack.set_visible_child_name("browser")
        self.discover_web.load_uri(uri)

    def _recommendation_feedback(self, uri, value, button):
        initial_label = "♥ Aimer" if value > 0 else "Moins"
        self._button_busy(button, "Enregistrement…")
        self.suggestion_status.set_text("Votre préférence améliore les prochains résultats…")

        def update():
            self.backend.recommendation_feedback(uri, value)
            return self.backend.recommendation_data()

        def ready(data):
            if value > 0:
                self.suggestion_status.set_text("Aimé ♥ · suggestions adaptées")
                self._success_animation(
                    button, "♥ Aimé ✓", "success-like",
                    lambda: self._restore_label(button, initial_label),
                    after=lambda: self._recommendations_ready(data),
                )
            else:
                self._recommendations_ready(data)
            return False

        def failed(error):
            self._restore_label(button, initial_label)
            return self._recommendations_failed(error)

        self.tasks.run(update, ready, failed)

    def _download_recommendation(self, item, button):
        self._button_busy(button, "Téléchargement…")
        height = DOWNLOAD_QUALITIES[
            self.suggestion_download_quality.get_selected()
        ][1]
        target = "automatique" if height == 0 else f"{height}p"
        self.suggestion_status.set_text(
            f"Téléchargement de « {item.title} » · qualité {target}…"
        )
        self.suggestion_firefox_retry.set_visible(False)

        def finished(outcome):
            if outcome.path is None:
                self._restore_label(button, "↓ Télécharger")
                self.suggestion_status.set_text(
                    f"Téléchargement impossible : {outcome.message}"
                )
                if outcome.source == "authentication-required":
                    self.last_failed_download = (
                        item.uri, item.title, height, "suggestion"
                    )
                    self.suggestion_firefox_retry.set_visible(True)
            else:
                self.suggestion_firefox_retry.set_visible(False)
                self.suggestion_status.set_text(
                    f"Ajouté à la bibliothèque : {outcome.path.name}"
                )
                self._success_animation(
                    button, "✓ Téléchargé", "success-download",
                    lambda: self._restore_label(button, "↓ Télécharger"),
                )
                self.reload(scan=False)
            return False

        def failed(error):
            self._restore_label(button, "↓ Télécharger")
            self.suggestion_status.set_text(f"Téléchargement impossible : {error}")
            return False

        self.tasks.run(
            lambda: self.backend.download_discovery_page(
                item.uri, item.title, height
            ),
            finished, failed,
        )

    def _playlists_page(self):
        box = self._empty_page("Playlists", "Créez une liste puis ajoutez-y le wallpaper sélectionné.")
        controls = Gtk.Box(spacing=8)
        self.playlist_name = Gtk.Entry(placeholder_text="Nom de la playlist", hexpand=True)
        create = Gtk.Button(label="Créer", css_classes=["suggested-action"])
        create.connect("clicked", self._create_playlist)
        controls.append(self.playlist_name)
        controls.append(create)
        box.append(controls)
        self.playlist_list = Gtk.ListBox(css_classes=["boxed-list"])
        box.append(self.playlist_list)
        return box

    def _recent_page(self):
        box = self._empty_page("Récents", "Historique local par date et écran.")
        self.recent_list = Gtk.ListBox(css_classes=["boxed-list"])
        box.append(self.recent_list)
        return box

    def _monitors_page(self):
        box = self._empty_page("Écrans", "Écrans Hyprland détectés, sans polling.")
        self.monitor_list = Gtk.ListBox(css_classes=["boxed-list"])
        box.append(self.monitor_list)
        return box

    def _settings_page(self):
        box = self._empty_page("Réglages", "Cache, téléchargement, thème, automatisation et options avancées.")
        self.cache_label = Gtk.Label(label="Cache : calcul à la demande", xalign=0)
        box.append(self.cache_label)
        calculate = Gtk.Button(label="Mesurer le cache", halign=Gtk.Align.START)
        calculate.connect("clicked", self._cache_stats)
        box.append(calculate)
        box.append(Gtk.Separator(margin_top=8, margin_bottom=4))
        box.append(Gtk.Label(label="Téléchargeur YouTube", xalign=0,
                             css_classes=["title-2"]))
        self.downloader_diagnostic = Gtk.Label(
            label="Diagnostic à la demande", xalign=0, selectable=True,
            wrap=True, css_classes=["dim-label"],
        )
        box.append(self.downloader_diagnostic)
        diagnose = Gtk.Button(label="Diagnostiquer le téléchargeur",
                              halign=Gtk.Align.START)
        diagnose.connect("clicked", self._diagnose_downloader)
        box.append(diagnose)
        return box

    @staticmethod
    def _empty_page(title, subtitle):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                      margin_top=20, margin_bottom=20, margin_start=20, margin_end=20)
        box.append(Gtk.Label(label=title, xalign=0, css_classes=["title-1"]))
        box.append(Gtk.Label(label=subtitle, xalign=0, wrap=True,
                             css_classes=["dim-label"]))
        return box

    def _inspector(self):
        scroll = Gtk.ScrolledWindow(width_request=350)
        scroll.add_css_class("inspector-pane")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                      margin_top=20, margin_bottom=20, margin_start=18, margin_end=18)
        box.append(Gtk.Label(label="Inspecteur", xalign=0, css_classes=["title-2"]))
        self.preview = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, height_request=190,
                                   css_classes=["inspector-preview"])
        box.append(self.preview)
        self.selected_label = Gtk.Label(label="Sélectionnez un wallpaper", xalign=0,
                                        wrap=True, css_classes=["heading"])
        self.media_details = Gtk.Label(label="", xalign=0, wrap=True,
                                       css_classes=["dim-label"])
        box.append(self.selected_label)
        box.append(self.media_details)
        self.output = Gtk.DropDown.new_from_strings(["Tous les écrans (*)"])
        box.append(self._section("Écran", self.output))
        apply_button = Gtk.Button(label="Appliquer le fond",
                                  css_classes=["suggested-action", "pill"])
        apply_button.connect("clicked", self._action_clicked, "apply")
        box.append(apply_button)
        buttons = Gtk.Box(spacing=6, homogeneous=True)
        for label, action in (("Pause", "pause"), ("Reprendre", "resume"),
                              ("Relancer", "restart")):
            button = Gtk.Button(label=label)
            button.connect("clicked", self._action_clicked, action)
            buttons.append(button)
        box.append(buttons)
        self.favorite = Gtk.ToggleButton(label="☆ Favori")
        self.favorite.connect("toggled", self._favorite_changed)
        box.append(self.favorite)
        self.volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.volume.set_value(0)
        self.volume.connect("change-value", self._scale_changed, "volume")
        box.append(self._section("Volume", self.volume))
        self.speed = Gtk.DropDown.new_from_strings(["0.5×", "0.75×", "1×", "1.25×", "1.5×"])
        self.speed.set_selected(2)
        self.speed.connect("notify::selected", self._speed_changed)
        box.append(self._section("Vitesse", self.speed))
        self.mute = Gtk.Switch(active=True)
        self.mute.connect("notify::active", self._switch_changed, "mute")
        self.loop = Gtk.Switch(active=True)
        self.loop.connect("notify::active", self._switch_changed, "loop")
        box.append(self._section("Muet", self.mute))
        box.append(self._section("Boucle", self.loop))
        self.profile = Gtk.DropDown.new_from_strings(["AUTO", "ECO", "BALANCED", "QUALITY"])
        self.profile.connect("notify::selected", self._profile_changed)
        box.append(self._section("Performance", self.profile))
        self.theme_mode = Gtk.DropDown.new_from_strings(["Désactivé", "À l’application", "Toujours"])
        box.append(self._section("Synchronisation du thème", self.theme_mode))
        self.saturation = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -100, 100, 1)
        self.saturation.connect("change-value", self._color_changed)
        box.append(self._section("Couleurs · saturation", self.saturation))
        self.status = Gtk.Label(label="", xalign=0, wrap=True, css_classes=["dim-label"])
        box.append(self.status)
        scroll.set_child(box)
        return scroll

    @staticmethod
    def _section(title, child):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                      css_classes=["inspector-section"])
        box.append(Gtk.Label(label=title, xalign=0, css_classes=["heading"]))
        box.append(child)
        return box

    def _page_selected(self, _list, row):
        if row is None:
            return
        self.pages.set_visible_child_name(row.page_name)
        self.search.set_visible(row.page_name in {"library", "favorites"})
        self.media_filter.set_visible(row.page_name in {"library", "favorites"})
        self.inspector_split.set_show_sidebar(
            row.page_name in {"library", "favorites"}
        )
        if row.page_name == "favorites":
            self.reload(scan=False)
        elif row.page_name == "discover" and not self.recommendations_loaded:
            self._load_recommendations()
        elif row.page_name == "playlists":
            self._refresh_playlists()
        elif row.page_name == "recent":
            self._refresh_recent()
        elif row.page_name == "monitors":
            self.refresh_outputs()
        elif row.page_name == "settings":
            self._diagnose_downloader()

    def reload(self, *, scan):
        query = self.search.get_text() if hasattr(self, "search") else ""
        kinds = ("all", "video", "image")
        kind = kinds[self.media_filter.get_selected()] if hasattr(self, "media_filter") else "all"
        self._busy("Chargement de la bibliothèque…")
        self.tasks.run(
            lambda: self._load_library_data(scan, query, kind),
            self._library_loaded, self._failed,
        )

    def _load_library_data(self, scan, query, kind):
        if scan:
            self.backend.refresh_library(scan=True)
        return (self.backend.search(query, kind=kind),
                self.backend.search(query, kind=kind, favorites=True))

    def _library_loaded(self, result):
        items, favorites = result
        self._fill_flow(self.library_flow, items)
        self._fill_flow(self.favorite_flow, favorites)
        self.library_count.set_text(f"{len(items)} média(s)")
        self._busy(f"{len(items)} wallpaper(s)")
        return False

    def _fill_flow(self, flow, items):
        while child := flow.get_first_child():
            flow.remove(child)
        for item in items:
            flow.append(WallpaperCard(item, self.select, self.apply_item, self._context_menu))

    def select(self, item):
        self.selected = item
        self.selected_label.set_text(item.title)
        self.media_details.set_text(_details(item))
        self.favorite.handler_block_by_func(self._favorite_changed)
        self.favorite.set_active(item.favorite)
        self.favorite.set_label("★ Favori" if item.favorite else "☆ Favori")
        self.favorite.handler_unblock_by_func(self._favorite_changed)
        preview = item.thumbnail_path if item.thumbnail_path and item.thumbnail_path.is_file() else (
            item.path if item.media_type.value == "image" else None
        )
        if preview:
            self.preview.set_filename(str(preview))
        else:
            self.preview.set_paintable(None)
            if item.id not in self.thumbnail_requests:
                self.thumbnail_requests.add(item.id)
                self.tasks.run(
                    lambda: self.backend.ensure_thumbnail(item.id),
                    lambda path, item_id=item.id: self._thumbnail_loaded(item_id, path),
                    self._failed,
                )

    def _thumbnail_loaded(self, item_id, path):
        self.thumbnail_requests.discard(item_id)
        if self.selected is not None and self.selected.id == item_id:
            self.preview.set_filename(str(path))
        self.reload(scan=False)
        return False

    def apply_item(self, item):
        self.select(item)
        theme_modes = ("off", "on_apply", "always")
        profiles = ("auto", "eco", "balanced", "quality")
        self._dispatch(
            lambda: self.backend.apply(
                item.id, self._output(),
                theme_mode=theme_modes[self.theme_mode.get_selected()],
                performance_profile=profiles[self.profile.get_selected()],
            ),
            "Wallpaper appliqué",
        )

    def _context_menu(self, card, x, y):
        menu = Gtk.Popover()
        menu.set_parent(card)
        button = Gtk.Button(label="Ajouter à la première playlist")
        button.connect("clicked", lambda _button: self._add_first_playlist(card.item))
        menu.set_child(button)
        menu.popup()

    def _action_clicked(self, _button, action):
        if action == "apply":
            if self.selected:
                self.apply_item(self.selected)
            return
        self._dispatch(lambda: self.backend.playback(action, self._output()), f"{action} envoyé")

    def _favorite_changed(self, button):
        if not self.selected:
            return
        value = button.get_active()
        self._dispatch(lambda: self.backend.set_favorite(self.selected.id, value),
                       "Favori enregistré", refresh=True)

    def _scale_changed(self, _scale, _scroll, value, action):
        self._dispatch(lambda: self.backend.playback(action, self._output(), value), "Réglage appliqué")
        return False

    def _speed_changed(self, dropdown, _param):
        values = (0.5, 0.75, 1.0, 1.25, 1.5)
        self._dispatch(lambda: self.backend.playback("speed", self._output(), values[dropdown.get_selected()]),
                       "Vitesse appliquée")

    def _switch_changed(self, switch, _param, action):
        self._dispatch(lambda: self.backend.playback(action, self._output(), switch.get_active()),
                       "Réglage appliqué")

    def _profile_changed(self, dropdown, _param):
        values = ("auto", "eco", "balanced", "quality")
        self._dispatch(lambda: self.backend.playback("profile", self._output(), values[dropdown.get_selected()]),
                       "Profil appliqué")

    def _color_changed(self, _scale, _scroll, value):
        color = {"name": "GUI", "saturation": int(value)}
        self._dispatch(lambda: self.backend.playback("color", self._output(), color), "Couleurs appliquées")
        return False

    def _output(self):
        index = self.output.get_selected()
        return self.output_names[index] if index < len(self.output_names) else "*"

    def refresh_outputs(self):
        self.tasks.run(self.backend.outputs, self._outputs_loaded, self._failed)

    def _outputs_loaded(self, monitors):
        self.output_names = ["*", *(item.name for item in monitors)]
        labels = ["Tous les écrans (*)", *(item.name for item in monitors)]
        self.output.set_model(Gtk.StringList.new(labels))
        while child := self.monitor_list.get_first_child():
            self.monitor_list.remove(child)
        for monitor in monitors:
            resolution = f"{monitor.width or '?'}×{monitor.height or '?'} · {monitor.refresh_rate or '?'} Hz"
            self.monitor_list.append(Adw.ActionRow(title=monitor.name, subtitle=resolution))
        return False

    def _create_playlist(self, _button):
        name = self.playlist_name.get_text().strip()
        if name:
            self._dispatch(lambda: self.backend.create_playlist(name), "Playlist créée",
                           after=self._refresh_playlists)

    def _refresh_playlists(self):
        self.tasks.run(
            lambda: [(playlist, len(self.backend.playlists.items(playlist.id)))
                     for playlist in self.backend.playlists.list()],
            self._playlists_loaded, self._failed,
        )

    def _playlists_loaded(self, playlists):
        while child := self.playlist_list.get_first_child():
            self.playlist_list.remove(child)
        for playlist, count in playlists:
            row = Adw.ActionRow(title=playlist.name,
                                subtitle=f"{count} élément(s) · {playlist.mode.value}")
            play = Gtk.Button(icon_name="media-skip-forward-symbolic", valign=Gtk.Align.CENTER)
            play.connect("clicked", lambda _button, pid=playlist.id: self._play_next(pid))
            row.add_suffix(play)
            self.playlist_list.append(row)
        return False

    def _add_first_playlist(self, item):
        def add():
            lists = self.backend.playlists.list()
            if not lists:
                raise ValueError("Créez d’abord une playlist")
            return self.backend.add_to_playlist(lists[0].id, item.id)
        self._dispatch(add,
                       "Ajouté à la playlist", after=self._refresh_playlists)

    def _play_next(self, playlist_id):
        self._dispatch(lambda: self.backend.play_next(playlist_id, self._output()),
                       "Wallpaper suivant appliqué", after=self._refresh_recent)

    def _refresh_recent(self):
        def load():
            result = []
            for entry in self.backend.history.list(limit=100):
                wallpaper = (self.backend.library.get(entry.wallpaper_id)
                             if entry.wallpaper_id else None)
                result.append((entry, wallpaper))
            return result
        self.tasks.run(load, self._recent_loaded, self._failed)

    def _recent_loaded(self, entries):
        while child := self.recent_list.get_first_child():
            self.recent_list.remove(child)
        for entry, wallpaper in entries:
            self.recent_list.append(Adw.ActionRow(
                title=wallpaper.title if wallpaper else "Wallpaper indisponible",
                subtitle=f"{entry.output} · {entry.started_at:%Y-%m-%d %H:%M} · {entry.reason}",
            ))
        return False

    def _cache_stats(self, _button):
        manager = CacheManager(self.backend.paths)
        self.tasks.run(manager.stats, self._cache_loaded, self._failed)

    def _cache_loaded(self, stats):
        size = stats["total_size"]
        self.cache_label.set_text(f"Cache : {size / (1024 * 1024):.1f} MiB")
        return False

    def _diagnose_downloader(self, _button=None):
        self.downloader_diagnostic.set_text("Vérification du téléchargeur…")
        self.tasks.run(
            self.backend.discovery_download_diagnostics,
            self._downloader_diagnostic_ready,
            lambda error: self.downloader_diagnostic.set_text(f"Erreur : {error}") or False,
        )

    def _downloader_diagnostic_ready(self, data):
        mark = lambda value: "✓" if value else "✗"
        profile = data["profile"]
        self.downloader_diagnostic.set_text(
            f"yt-dlp  {mark(data['yt_dlp'])}  {data['yt_dlp_version']}\n"
            f"Environnement privé  {mark(data['private_environment'])}\n"
            f"Deno  {mark(data['deno'])}  {data['deno_version']}\n"
            f"FFmpeg  {mark(data['ffmpeg'])}\n"
            f"Session Firefox  {mark(data['firefox_session'])}\n"
            f"Qualité automatique  {profile.target_height}p · {profile.reason}"
        )
        return False

    def _dispatch(self, operation, message, *, refresh=False, after=None):
        self._busy("Application…")

        def done(_result):
            self._busy(message)
            if refresh:
                self.reload(scan=False)
            if after:
                after()
            return False

        self.tasks.run(operation, done, self._failed)

    def _busy(self, text):
        self.status.set_text(text)

    def _failed(self, error):
        self._busy(f"Erreur : {error}")
        return False

    def _close(self, _window):
        self.tasks.close()
        return False


class EngineApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_startup(self):
        Adw.Application.do_startup(self)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        provider = Gtk.CssProvider()
        provider.load_from_string(STYLE)
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def do_activate(self):
        window = self.props.active_window or EngineWindow(self)
        window.present()


def main() -> int:
    return EngineApplication().run()
