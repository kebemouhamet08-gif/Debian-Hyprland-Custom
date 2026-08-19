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


def pericored_inventory():
    socket_path = os.environ.get(
        "PERIPHX_SOCKET",
        os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "periphx", "pericored.sock"),
    )
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1)
            client.connect(socket_path)
            client.sendall(b'{"method":"ListDevices"}\n')
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
        "touchpad": ("Pavés tactiles", "Périphériques tactiles vus par pericored", "input"),
        "gamepad": ("Manettes", "Périphériques gamepad vus par pericored", "gamepad"),
        "monitor": ("Écrans", "Sorties écran vues par pericored", "display"),
        "gpu": ("Cartes graphiques", "GPU vus par pericored", "component"),
        "hid": ("HID", "Périphériques HID vus par pericored", "usb"),
        "unknown": ("Autres périphériques", "Périphériques vus par pericored", "usb"),
    }
    for device in devices:
        device_class = device.get("class", "unknown")
        title, subtitle, kind = labels.get(device_class, labels["unknown"])
        identifier = device.get("id", "")
        details = " · ".join(filter(None, (
            device.get("manufacturer"),
            device.get("vendor_id"),
            device.get("product_id"),
            identifier,
        )))
        grouped.setdefault((title, subtitle, kind), []).append(
            f"{device.get('name', 'Périphérique')} · {details}"
        )
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
    return groups


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
            "Une vue Debian pour les périphériques USB, HID, écrans et manettes.",
        ))
        self.overview_status = Gtk.Label(label="Détection en cours…", xalign=0,
                                         wrap=True, css_classes=["dim-label"])
        self.overview_content.append(self.overview_status)
        self.overview_cards = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.overview_content.append(self.overview_cards)
        self.overview_content.append(Gtk.Label(
            label="Les protocoles RGB propriétaires et les macros nécessitent un pilote "
                  "compatible et une permission explicite.",
            xalign=0, wrap=True, css_classes=["dim-label"],
        ))
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self.overview_content)
        return scroll

    def build_devices(self):
        self.device_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                                      margin_top=24, margin_bottom=24,
                                      margin_start=28, margin_end=28)
        self.device_groups_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.device_content.append(self.device_groups_box)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self.device_content)
        return scroll

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