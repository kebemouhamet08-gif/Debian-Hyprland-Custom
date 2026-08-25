#!/usr/bin/env python3

import json
import os
import shutil
import socket
import subprocess
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk


APP_ID = "io.github.kebemouhamet08.PeriphX"
MANAGED_DEVICE_CLASSES = ("keyboard", "mouse", "gamepad")


def is_external_peripheral(device):
    """Limit PeriphX management to external input peripherals."""
    device_class = device.get("class", "unknown")
    if device_class not in MANAGED_DEVICE_CLASSES:
        return False

    identity = " ".join(str(device.get(field) or "") for field in (
        "connection", "syspath", "id", "name",
    )).casefold()
    if any(marker in identity for marker in (
        "usb", "bluetooth", "wireless", "receiver", "dongle", "2.4g",
    )):
        return True
    if any(marker in identity for marker in (
        "i8042", "platform", "serio", "internal", "built-in", "interne",
    )):
        return False

    # A game controller without transport metadata is still treated as external;
    # keyboards and mice must provide positive external-device evidence.
    return device_class == "gamepad"


def pericored_inventory():
    socket_path = os.environ.get(
        "PERIPHX_SOCKET",
        os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "periphx", "pericored.sock"),
    )
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1)
            client.connect(socket_path)
            client.sendall(b'{"method":"list_devices","request_id":"gui"}\n')
            response = client.makefile("rb").readline()
        payload = json.loads(response)
        if payload.get("ok"):
            return payload["result"].get("devices", [])
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        pass
    return None


def daemon_device_groups():
    devices = pericored_inventory()
    if devices is None:
        return None
    grouped = {}
    labels = {
        "keyboard": ("Claviers", "Périphériques clavier vus par pericored", "input"),
        "mouse": ("Souris", "Périphériques souris vus par pericored", "input"),
        "gamepad": ("Manettes", "Périphériques gamepad vus par pericored", "gamepad"),
    }
    for device_class in MANAGED_DEVICE_CLASSES:
        title, subtitle, kind = labels[device_class]
        grouped[(title, subtitle, kind)] = []
    for device in devices:
        device_class = device.get("class", "unknown")
        if not is_external_peripheral(device):
            continue
        title, subtitle, kind = labels[device_class]
        identifier = device.get("id", "")
        details = " · ".join(filter(None, (
            device.get("manufacturer"),
            device.get("vendor_id"),
            device.get("product_id"),
            identifier,
        )))
        item = dict(device)
        item["display_label"] = f"{device.get('name', 'Périphérique')} · {details}"
        grouped.setdefault((title, subtitle, kind), []).append(item)
    return [(title, subtitle, items, kind) for (title, subtitle, kind), items in grouped.items()]


def run_command(*command, timeout=3):
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip()


def command_available(command):
    return shutil.which(command) is not None


def bluetooth_sysfs_devices():
    devices = []
    root = Path("/sys/class/bluetooth")
    if not root.is_dir():
        return devices
    for entry in sorted(root.iterdir()):
        if not entry.name.startswith("hci") or ":" not in entry.name:
            continue
        address = entry / "address"
        label = entry / "name"
        value = address.read_text(encoding="utf-8").strip() if address.is_file() else entry.name
        name = label.read_text(encoding="utf-8").strip() if label.is_file() else ""
        devices.append(f"{name or 'Bluetooth'} · {value} · connecté")
    return devices


def sysfs_input_devices():
    devices = []
    root = Path("/sys/class/input")
    if not root.is_dir():
        return devices
    for name_file in sorted(root.glob("event*/device/name")):
        event_name = name_file.parts[-3]
        event_node = f"/dev/input/{event_name}"
        try:
            label = name_file.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        properties = run_command("udevadm", "info", "--query=property", "--name", event_node)
        property_map = dict(
            line.split("=", 1) for line in properties.splitlines() if "=" in line
        )
        is_gamepad = property_map.get("ID_INPUT_GAMEPAD") == "1"
        is_joystick = property_map.get("ID_INPUT_JOYSTICK") == "1"
        name_match = any(word in label.casefold() for word in (
            "gamepad", "joystick", "controller", "manette", "xbox", "dualshock",
            "playstation", "steam deck",
        ))
        if is_gamepad or is_joystick or name_match:
            devices.append(f"{label} · {input_scope(label)} · {event_node}")
    return devices


def input_scope(label):
    text = label.casefold()
    internal_markers = (
        "at translated set 2 keyboard", "internal", "built-in", "platform",
        "i8042", "lid switch", "video bus",
    )
    external_markers = (
        "usb", "bluetooth", "wireless", "receiver", "2.4g", "dongle",
    )
    if any(marker in text for marker in internal_markers):
        return "interne"
    if any(marker in text for marker in external_markers):
        return "externe"
    return "origine inconnue"


def device_groups():
    daemon_groups = daemon_device_groups()
    if daemon_groups is not None:
        return daemon_groups
    groups = []
    usb = run_command("lsusb")
    usb_items = [line for line in usb.splitlines() if line.strip()]
    groups.append(("USB et HID", "Périphériques USB détectés par le noyau", usb_items,
                   "usb"))

    input_output = run_command("libinput", "list-devices")
    if not input_output:
        input_output = run_command("evtest", "--list-devices")
    input_items = []
    for line in input_output.splitlines():
        line = line.strip()
        if line.startswith("Device:"):
            label = line.removeprefix("Device:").strip()
            input_items.append(f"{label} · {input_scope(label)}")
    if not input_items:
        input_items = [line.strip() for line in input_output.splitlines() if line.strip()]
    if not input_items:
        input_items = [
            f"{line} · externe"
            for line in usb_items
            if any(word in line.casefold() for word in (
                "keyboard", "mouse", "souris", "clavier", "trackpad", "touchpad",
            ))
        ]
    input_group_index = len(groups)
    groups.append(("Clavier et souris", "Événements d’entrée exposés par libinput/evdev",
                   input_items, "input"))

    monitors = run_command("hyprctl", "monitors", "-j")
    monitor_items = []
    try:
        for monitor in json.loads(monitors):
            monitor_items.append(
                f"{monitor.get('name', 'écran')} · {monitor.get('make', '')} "
                f"{monitor.get('model', '')} · {monitor.get('width', '?')}x"
                f"{monitor.get('height', '?')}"
            )
    except (json.JSONDecodeError, TypeError):
        monitor_items = [line for line in monitors.splitlines() if line.strip()]
    groups.append(("Écrans", "Sorties Hyprland et résolution active", monitor_items, "display"))

    gamepads = run_command("evtest", "--list-devices")
    gamepad_items = [line.strip() for line in gamepads.splitlines()
                     if any(word in line.casefold() for word in ("gamepad", "joystick", "controller"))]
    sysfs_gamepads = sysfs_input_devices()
    for item in sysfs_gamepads:
        if item not in gamepad_items:
            gamepad_items.append(item)
    groups.append(("Manettes", "Périphériques joystick/gamepad exposés par evdev",
                   gamepad_items, "gamepad"))

    bluetooth_connected = run_command("bluetoothctl", "devices", "Connected")
    bluetooth_items = []
    for line in bluetooth_connected.splitlines():
        if line.strip():
            bluetooth_items.append(f"{line.strip()} · connecté")
    if not bluetooth_items:
        bluetooth_items = bluetooth_sysfs_devices()
    bluetooth_info = run_command("bluetoothctl", "show")
    bluetooth_root = Path("/sys/class/bluetooth")
    adapter_present = bluetooth_root.is_dir() and any(
        entry.name.startswith("hci") and ":" not in entry.name
        for entry in bluetooth_root.iterdir()
    )
    adapter_state = "activé" if "Powered: yes" in bluetooth_info else (
        "présent" if adapter_present else "désactivé ou absent"
    )
    if command_available("bluetoothctl") and not bluetooth_info and not bluetooth_items:
        adapter_state = "backend D-Bus indisponible"
        bluetooth_items = ["Bluetooth détecté, mais BlueZ ne répond pas"]
    bluetooth_input_items = [
        f"{line} · externe · Bluetooth"
        for line in bluetooth_items
        if any(word in line.casefold() for word in (
            "mouse", "souris", "keyboard", "clavier", "touchpad", "trackpad",
        ))
    ]
    if bluetooth_input_items:
        current_input_items = groups[input_group_index][2]
        groups[input_group_index] = (
            groups[input_group_index][0], groups[input_group_index][1],
            [*current_input_items, *bluetooth_input_items], groups[input_group_index][3],
        )
    groups.append(("Bluetooth", f"Appareils connus · adaptateur {adapter_state}",
                   bluetooth_items, "bluetooth"))

    components = []
    cpu = run_command("lscpu")
    for line in cpu.splitlines():
        if line.startswith("Model name:") or line.startswith("Nom de modèle:"):
            components.append(f"Processeur · {line.split(':', 1)[1].strip()}")
            break
    graphics = run_command("lspci", "-nn")
    for line in graphics.splitlines():
        lowered = line.casefold()
        if any(marker in lowered for marker in ("vga compatible controller", "3d controller", "display controller")):
            components.append(f"Carte graphique · {line.split(': ', 1)[-1]}")
    groups.append(("Composants système", "Processeur et carte graphique détectés par Linux",
                   components, "component"))
    managed_groups = []
    for title, subtitle, items, kind in groups:
        if title == "Clavier et souris":
            items = [item for item in items if input_scope(item) == "externe" or "· externe" in item]
            managed_groups.append((title, subtitle, items, kind))
        elif title == "Manettes":
            managed_groups.append((title, subtitle, items, kind))
    return managed_groups


def capability_rows():
    return [
        ("Luminosité écran", "ddcutil" if command_available("ddcutil") else "non installé",
         "DDC/CI"),
        ("Rétroéclairage RGB", "OpenRGB" if command_available("openrgb") else "non installé",
         "USB HID propriétaire"),
        ("Remappage clavier/souris", "libinput" if command_available("libinput") else "non installé",
         "evdev / uinput"),
        ("Manettes", "evtest" if command_available("evtest") else "non installé",
         "joydev / evdev"),
        ("Bluetooth", "bluetoothctl" if command_available("bluetoothctl") else "non installé",
         "BlueZ"),
        ("Profils", "V3 local", "JSON isolé"),
    ]


def icon_for_kind(kind):
    icons = {
        "usb": "drive-removable-media-symbolic",
        "input": "input-keyboard-symbolic",
        "display": "video-display-symbolic",
        "gamepad": "input-gaming-symbolic",
        "bluetooth": "bluetooth-active-symbolic",
        "component": "chip-symbolic",
    }
    return icons.get(kind, "computer-symbolic")


def icon_for_device(kind, label):
    if isinstance(label, dict):
        label = label.get("display_label") or label.get("name", "")
    text = label.casefold()
    if kind == "input":
        if any(word in text for word in ("mouse", "souris", "touchpad", "trackball")):
            return "input-mouse-symbolic"
        if any(word in text for word in ("keyboard", "clavier")):
            return "input-keyboard-symbolic"
    if kind == "gamepad" or any(word in text for word in ("gamepad", "joystick", "controller", "manette")):
        return "input-gaming-symbolic"
    if kind == "display" or any(word in text for word in ("monitor", "display", "screen", "écran")):
        return "video-display-symbolic"
    if kind == "usb":
        return "drive-removable-media-symbolic"
    if kind == "bluetooth":
        return "bluetooth-active-symbolic"
    if kind == "component":
        if "carte graphique" in text or "gpu" in text or "vga" in text or "display" in text:
            return "video-display-symbolic"
        return "chip-symbolic"
    return icon_for_kind(kind)


def device_item_label(item):
    if isinstance(item, dict):
        return item.get("display_label") or item.get("name", "Périphérique")
    return item


DEVICE_INTERFACES = {
    "keyboard": {
        "title": "Interface clavier",
        "description": "Touches, répétition, macros et éclairage exposés par le pilote.",
        "icon": "input-keyboard-symbolic",
        "features": (
            ("Touches", ("keyboard.buttons", "input.events", "hid.inspect")),
            ("Macros", ("keyboard.macros",)),
            ("Éclairage", ("lighting.rgb", "keyboard.backlight")),
        ),
    },
    "mouse": {
        "title": "Interface souris",
        "description": "Boutons, mouvement, DPI, fréquence et éclairage disponibles.",
        "icon": "input-mouse-symbolic",
        "features": (
            ("Boutons et mouvement", ("mouse.buttons", "input.events", "hid.inspect")),
            ("Sensibilité / DPI", ("mouse.dpi",)),
            ("Fréquence d’interrogation", ("mouse.polling_rate",)),
            ("Éclairage", ("lighting.rgb",)),
        ),
    },
    "gamepad": {
        "title": "Interface manette",
        "description": "Boutons, sticks, gâchettes, vibration et batterie disponibles.",
        "icon": "input-gaming-symbolic",
        "features": (
            ("Boutons", ("gamepad.buttons", "input.events", "hid.inspect")),
            ("Sticks et gâchettes", ("gamepad.axes", "input.events")),
            ("Vibration", ("gamepad.rumble",)),
            ("Batterie", ("battery.level",)),
        ),
    },
}


class DeviceCenter(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="PeriphX")
        self.set_default_size(980, 700)
        self.set_size_request(720, 480)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Actualiser")
        refresh.connect("clicked", lambda _button: self.refresh())
        header.pack_end(refresh)
        toolbar.add_top_bar(header)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_vexpand(True)
        self.stack.add_titled(self.build_overview(), "overview", "Vue d’ensemble")
        self.stack.add_titled(self.build_devices(), "devices", "Périphériques")
        self.stack.add_titled(self.build_display_link(), "display", "Affichage")
        self.stack.add_titled(self.build_capabilities(), "capabilities", "Capacités")
        switcher = Gtk.StackSwitcher(stack=self.stack)
        header.set_title_widget(switcher)
        toolbar.set_content(self.stack)
        self.set_content(toolbar)
        self.last_groups_signature = None
        self.refresh()
        self.refresh_timer_id = GLib.timeout_add(500, self.refresh_devices)

    def section(self, title, subtitle):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        box.append(Gtk.Label(label=title, xalign=0, css_classes=["title-2"]))
        box.append(Gtk.Label(label=subtitle, xalign=0, wrap=True, css_classes=["dim-label"]))
        return box

    def build_overview(self):
        self.overview_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                                        margin_top=24, margin_bottom=24,
                                        margin_start=28, margin_end=28)
        self.overview_content.append(self.section(
            "Centre de contrôle matériel",
            "Gestion des claviers, souris et manettes externes.",
        ))
        self.overview_status = Gtk.Label(label="Détection en cours…", xalign=0,
                                         wrap=True, css_classes=["dim-label"])
        self.overview_content.append(self.overview_status)
        self.overview_cards = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.overview_content.append(self.overview_cards)
        self.overview_content.append(Gtk.Label(
            label="Les périphériques internes et les pilotes du système restent gérés par "
                  "Debian. Les protocoles propriétaires nécessitent un pilote PeriphX compatible.",
            xalign=0, wrap=True, css_classes=["dim-label"],
        ))
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self.overview_content)
        return scroll

    def build_devices(self):
        self.devices_stack = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT,
        )
        self.device_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                                      margin_top=24, margin_bottom=24,
                                      margin_start=28, margin_end=28)
        self.device_groups_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.device_content.append(self.device_groups_box)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self.device_content)
        self.devices_stack.add_named(scroll, "list")

        self.device_detail_content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=14,
            margin_top=24, margin_bottom=24, margin_start=28, margin_end=28,
        )
        detail_scroll = Gtk.ScrolledWindow(vexpand=True)
        detail_scroll.set_child(self.device_detail_content)
        self.devices_stack.add_named(detail_scroll, "detail")
        return self.devices_stack

    def build_capabilities(self):
        self.capability_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                                          margin_top=24, margin_bottom=24,
                                          margin_start=28, margin_end=28)
        self.capability_content.append(self.section(
            "Capacités disponibles",
            "La V3 utilise les interfaces Debian standard et n’envoie aucune commande "
            "USB sans backend identifié.",
        ))
        self.capability_rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                           spacing=0, css_classes=["boxed-list"])
        self.capability_content.append(self.capability_rows_box)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self.capability_content)
        return scroll

    def build_display_link(self):
        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=16,
            margin_top=24, margin_bottom=24, margin_start=28, margin_end=28,
        )
        content.append(self.section(
            "Affichage et couleurs",
            "PeriphX ouvre le moteur couleur de MPVpaper Engine pour ajuster le fond "
            "vidéo de chaque écran sans modifier les applications ni le bureau entier.",
        ))
        features = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0,
                           css_classes=["boxed-list"])
        features.append(self.info_row(
            "Réglages essentiels", "Luminosité, contraste, gamma, saturation et teinte",
            "video-display-symbolic",
        ))
        features.append(self.info_row(
            "Balance des couleurs", "Température, rouge, vert et bleu via libavfilter",
            "applications-graphics-symbolic",
        ))
        features.append(self.info_row(
            "Aperçu instantané", "Communication directe avec mpv, sans redémarrer le fond",
            "media-playback-start-symbolic",
        ))
        content.append(features)
        open_colors = Gtk.Button(
            label="Ouvrir les couleurs dans MPVpaper Engine",
            css_classes=["suggested-action", "pill"],
            halign=Gtk.Align.START,
        )
        open_colors.connect("clicked", self.open_mpvpaper_colors)
        content.append(open_colors)
        self.display_link_status = Gtk.Label(label="", xalign=0, wrap=True,
                                             css_classes=["dim-label"])
        content.append(self.display_link_status)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(content)
        return scroll

    def open_mpvpaper_colors(self, _button):
        command = shutil.which("mpvpaper-engine")
        if not command:
            self.display_link_status.set_text("MPVpaper Engine n’est pas installé.")
            return
        try:
            subprocess.Popen(
                [command, "--colors"], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True,
            )
            self.display_link_status.set_text("Page Couleurs ouverte dans MPVpaper Engine.")
        except OSError as error:
            self.display_link_status.set_text(f"Impossible d’ouvrir MPVpaper Engine : {error}")

    def clear(self, box):
        box.set_focus_child(None)
        while child := box.get_first_child():
            box.remove(child)

    def info_row(self, title, subtitle, icon_name):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12,
                      margin_top=10, margin_bottom=10, margin_start=12, margin_end=12)
        row.set_focusable(False)
        row.append(Gtk.Image.new_from_icon_name(icon_name))
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        labels.append(Gtk.Label(label=title, xalign=0))
        labels.append(Gtk.Label(label=subtitle, xalign=0, wrap=True,
                                css_classes=["dim-label"]))
        row.append(labels)
        return row

    def selectable_device_row(self, item, kind):
        button = Gtk.Button(css_classes=["flat"])
        button.set_hexpand(True)
        button.set_child(self.info_row(
            device_item_label(item), "Sélectionner pour ouvrir son interface",
            icon_for_device(kind, item),
        ))
        button.connect("clicked", self.open_device, item)
        return button

    def detail_row(self, title, value, icon_name="emblem-system-symbolic"):
        return self.info_row(title, value or "Non disponible", icon_name)

    def open_device(self, _button, device):
        if not isinstance(device, dict):
            return
        self.selected_device_id = device.get("id")
        self.render_device_interface(device)
        self.devices_stack.set_visible_child_name("detail")

    def show_device_list(self, _button):
        self.selected_device_id = None
        self.devices_stack.set_visible_child_name("list")

    def render_device_interface(self, device):
        self.clear(self.device_detail_content)
        device_class = device.get("class", "unknown")
        interface = DEVICE_INTERFACES.get(device_class, {
            "title": "Interface du périphérique",
            "description": "Informations et capacités exposées par le pilote actif.",
            "icon": icon_for_device("usb", device),
            "features": (("Inspection", ("device.info", "hid.inspect")),),
        })

        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        back = Gtk.Button(icon_name="go-previous-symbolic", tooltip_text="Retour aux périphériques")
        back.connect("clicked", self.show_device_list)
        heading.append(back)
        heading.append(Gtk.Image.new_from_icon_name(interface["icon"]))
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        titles.append(Gtk.Label(
            label=device.get("name", "Périphérique"), xalign=0,
            css_classes=["title-1"], wrap=True,
        ))
        titles.append(Gtk.Label(
            label=interface["title"], xalign=0, css_classes=["dim-label"],
        ))
        heading.append(titles)
        self.device_detail_content.append(heading)
        self.device_detail_content.append(Gtk.Label(
            label=interface["description"], xalign=0, wrap=True,
            css_classes=["dim-label"],
        ))

        capabilities = set(device.get("capabilities") or [])
        self.device_detail_content.append(self.section(
            "Fonctions", "Les fonctions actives dépendent du pilote détecté.",
        ))
        features = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0,
                           css_classes=["boxed-list"])
        for label, required in interface["features"]:
            available = any(capability in capabilities for capability in required)
            state = "Disponible" if available else "Non pris en charge par ce pilote"
            icon = "emblem-ok-symbolic" if available else "action-unavailable-symbolic"
            features.append(self.detail_row(label, state, icon))
        self.device_detail_content.append(features)

        self.device_detail_content.append(self.section(
            "Connexion", "Identité et interfaces Linux utilisées par PeriphX.",
        ))
        connection = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0,
                             css_classes=["boxed-list"])
        connection.append(self.detail_row("Pilote", device.get("driver"), "applications-system-symbolic"))
        connection.append(self.detail_row("Transport", device.get("connection"), "network-wired-symbolic"))
        connection.append(self.detail_row(
            "Interfaces", "\n".join(device.get("nodes") or []), "drive-removable-media-symbolic",
        ))
        connection.append(self.detail_row(
            "Identifiant", device.get("id"), "dialog-information-symbolic",
        ))
        self.device_detail_content.append(connection)

    def refresh(self):
        groups = device_groups()
        total = sum(len(items) for _title, _subtitle, items, _kind in groups)
        source = "pericored" if pericored_inventory() is not None else "détection locale"
        self.overview_status.set_text(
            f"{total} élément(s) détecté(s) · source : {source} · actualisé maintenant"
        )
        groups_signature = tuple(
            (title, subtitle, tuple(items), kind)
            for title, subtitle, items, kind in groups
        )
        if groups_signature == self.last_groups_signature:
            return
        self.last_groups_signature = groups_signature
        self.clear(self.overview_cards)
        for title, _subtitle, items, kind in groups:
            self.overview_cards.append(self.info_row(
                title, f"{len(items)} détecté(s)", icon_for_kind(kind)
            ))

        self.clear(self.device_groups_box)
        for title, subtitle, items, kind in groups:
            self.device_groups_box.append(self.section(title, subtitle))
            device_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                  spacing=0, css_classes=["boxed-list"])
            if items:
                for item in items:
                    if isinstance(item, dict):
                        device_list.append(self.selectable_device_row(item, kind))
                    else:
                        device_list.append(self.info_row(
                            item, "", icon_for_device(kind, item)
                        ))
            else:
                device_list.append(Gtk.Label(label="Aucun périphérique détecté",
                                             margin_top=12, margin_bottom=12))
            self.device_groups_box.append(device_list)

        self.clear(self.capability_rows_box)
        for title, state, backend in capability_rows():
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12,
                          margin_top=8, margin_bottom=8, margin_start=12, margin_end=12)
            row.set_focusable(False)
            labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
            labels.append(Gtk.Label(label=title, xalign=0))
            labels.append(Gtk.Label(label=f"Backend : {backend}", xalign=0,
                                    css_classes=["dim-label"]))
            row.append(labels)
            state_label = Gtk.Label(label=state, css_classes=[
                "success" if state not in ("non installé",) else "dim-label"
            ], valign=Gtk.Align.CENTER)
            row.append(state_label)
            self.capability_rows_box.append(row)

    def refresh_devices(self):
        if not self.get_visible():
            return True
        self.refresh()
        return True


class DeviceApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        window = self.props.active_window or DeviceCenter(self)
        window.present()


if __name__ == "__main__":
    raise SystemExit(DeviceApplication().run())
