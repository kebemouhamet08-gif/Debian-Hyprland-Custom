#!/usr/bin/env python3

import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk


APP_ID = "io.github.kebemouhamet08.PeriphX"
MANAGED_DEVICE_CLASSES = ("keyboard", "mouse", "gamepad")
NO_DAEMON_CHECK = object()

HID_KEY_NAMES = {
    4: "A", 5: "B", 6: "C", 7: "D", 8: "E", 9: "F", 10: "G",
    11: "H", 12: "I", 13: "J", 14: "K", 15: "L", 16: "M",
    17: "N", 18: "O", 19: "P", 20: "Q", 21: "R", 22: "S",
    23: "T", 24: "U", 25: "V", 26: "W", 27: "X", 28: "Y",
    29: "Z", 30: "1", 31: "2", 32: "3", 33: "4", 34: "5",
    35: "6", 36: "7", 37: "8", 38: "9", 39: "0", 40: "Entrée",
    41: "Échap", 42: "Retour", 43: "Tab", 44: "Espace", 57: "Verr. Maj",
    58: "F1", 59: "F2", 60: "F3", 61: "F4", 62: "F5", 63: "F6",
    64: "F7", 65: "F8", 66: "F9", 67: "F10", 68: "F11", 69: "F12",
}
HID_MODIFIER_NAMES = (
    "Ctrl G", "Maj G", "Alt G", "Super G",
    "Ctrl D", "Maj D", "Alt D", "Super D",
)
INPUT_EVENT = struct.Struct("@llHHi")
LINUX_KEY_NAMES = {
    1: "Échap", 2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6",
    8: "7", 9: "8", 10: "9", 11: "0", 14: "Retour", 15: "Tab",
    16: "A", 17: "Z", 18: "E", 19: "R", 20: "T", 21: "Y", 22: "U",
    23: "I", 24: "O", 25: "P", 28: "Entrée", 29: "Ctrl G", 30: "Q",
    31: "S", 32: "D", 33: "F", 34: "G", 35: "H", 36: "J", 37: "K",
    38: "L", 42: "Maj G", 44: "W", 45: "X", 46: "C", 47: "V",
    48: "B", 49: "N", 50: "M", 54: "Maj D", 56: "Alt G", 57: "Espace",
    58: "Verr. Maj", 59: "F1", 60: "F2", 61: "F3", 62: "F4", 63: "F5",
    64: "F6", 65: "F7", 66: "F8", 67: "F9", 68: "F10", 87: "F11",
    88: "F12", 97: "Ctrl D", 100: "Alt Gr", 103: "Haut", 105: "Gauche",
    106: "Droite", 108: "Bas", 125: "Super G", 126: "Super D",
    272: "Clic gauche", 273: "Clic droit", 274: "Clic milieu",
    275: "Bouton latéral", 276: "Bouton arrière",
    304: "Manette A", 305: "Manette B", 307: "Manette X", 308: "Manette Y",
    310: "LB", 311: "RB", 314: "Select", 315: "Start", 316: "Mode",
    317: "Stick gauche", 318: "Stick droit",
}
REL_NAMES = {0: "X", 1: "Y", 6: "molette horizontale", 8: "molette"}
ABS_NAMES = {
    0: "Stick gauche X", 1: "Stick gauche Y", 2: "Gâchette gauche",
    3: "Stick droit X", 4: "Stick droit Y", 5: "Gâchette droite",
    16: "Croix X", 17: "Croix Y",
}


def decode_input_event(event):
    event_type = event.get("type")
    code = event.get("code", 0)
    value = event.get("value", 0)
    if event_type == 1:
        name = LINUX_KEY_NAMES.get(code, f"Bouton {code}")
        action = {0: "relâché", 1: "pressé", 2: "répété"}.get(value, f"valeur {value}")
        return f"{name} · {action}"
    if event_type == 2:
        return f"{REL_NAMES.get(code, f'Mouvement {code}')} · {value:+d}"
    if event_type == 3:
        return f"{ABS_NAMES.get(code, f'Axe {code}')} · {value}"
    return None


def event_nodes(device):
    return [node for node in device.get("nodes", []) if node.startswith("/dev/input/event")]


def normalized_event_text(event):
    control = str(event.get("control") or "contrôle inconnu")
    label = control.rsplit(".", 1)[-1].replace("_", " ").title()
    kind = event.get("kind")
    raw = int(event.get("raw_value") or 0)
    if kind in ("key", "button"):
        action = {0: "relâché", 1: "pressé", 2: "répété"}.get(raw, f"valeur {raw}")
        return f"{label} · {action}"
    normalized = event.get("normalized_value")
    if normalized is not None:
        return f"{label} · {float(normalized):+.3f} (brut {raw})"
    return f"{label} · {raw:+d}"


def report_bytes(report):
    try:
        data = bytes.fromhex(str(report.get("raw_hex") or ""))
    except ValueError:
        return b""
    report_id = report.get("report_id")
    if report_id is not None and data and data[0] == report_id:
        return data[1:]
    return data


def keyboard_report_keys(report):
    data = report_bytes(report)
    if len(data) < 2:
        return set()
    keys = {
        HID_MODIFIER_NAMES[index]
        for index in range(8) if data[0] & (1 << index)
    }
    keys.update(HID_KEY_NAMES.get(code, f"HID 0x{code:02X}")
                for code in data[2:] if code)
    return keys


def signed_byte(value):
    return value - 256 if value > 127 else value


def summarize_hid_report(device_class, report):
    data = report_bytes(report)
    if device_class == "keyboard":
        keys = sorted(keyboard_report_keys(report))
        return "Touches : " + (" + ".join(keys) if keys else "aucune")
    if device_class == "mouse" and data:
        buttons = [str(index + 1) for index in range(8) if data[0] & (1 << index)]
        movement = []
        if len(data) >= 3:
            movement = [f"X {signed_byte(data[1]):+d}", f"Y {signed_byte(data[2]):+d}"]
        if len(data) >= 4 and signed_byte(data[3]):
            movement.append(f"molette {signed_byte(data[3]):+d}")
        return " · ".join([
            f"Boutons : {', '.join(buttons) if buttons else 'aucun'}", *movement,
        ])
    report_id = report.get("report_id")
    identifier = "sans ID" if report_id is None else f"report 0x{report_id:02X}"
    return f"{identifier} · {len(data)} octet(s) · {data.hex(' ')[:120]}"


def is_external_peripheral(device):
    """Limit PeriphX management to external input peripherals."""
    device_classes = set(device.get("classes") or [device.get("class", "unknown")])
    if not device_classes.intersection(MANAGED_DEVICE_CLASSES):
        return False
    if isinstance(device.get("external"), bool):
        return device["external"]

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
    return "gamepad" in device_classes


def pericored_socket_path():
    socket_path = os.environ.get("PERIPHX_SOCKET")
    if not socket_path:
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        socket_path = os.path.join(runtime_dir, "periphx", "pericored.sock") \
            if runtime_dir else "/tmp/periphx-pericored.sock"
    return socket_path


def pericored_request(method, params=None, request_id="gui"):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        client.connect(pericored_socket_path())
        client.sendall((json.dumps({
            "method": method, "request_id": request_id, "params": params or {},
        }) + "\n").encode())
        response = client.makefile("rb").readline()
    payload = json.loads(response)
    if not payload.get("ok"):
        error = payload.get("error") or {}
        raise RuntimeError(error.get("message", "erreur IPC pericored"))
    return payload.get("result") or {}


def pericored_inventory():
    try:
        return pericored_request("list_devices").get("devices", [])
    except (OSError, RuntimeError, json.JSONDecodeError, KeyError, TypeError):
        pass
    return None


def daemon_device_groups(devices=None):
    if devices is None:
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
        if not is_external_peripheral(device):
            continue
        identifier = device.get("id", "")
        details = " · ".join(filter(None, (
            device.get("manufacturer"),
            device.get("vendor_id"),
            device.get("product_id"),
            identifier,
        )))
        device_classes = device.get("classes") or [device.get("class", "unknown")]
        for device_class in MANAGED_DEVICE_CLASSES:
            if device_class not in device_classes:
                continue
            title, subtitle, kind = labels[device_class]
            item = dict(device)
            item["class"] = device_class
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


def periphx_cli_command():
    local = Path(__file__).with_name("periphx.py")
    if local.is_file():
        return [sys.executable, str(local)]
    installed = shutil.which("periphx-cli")
    if installed:
        return [installed]
    fallback = Path.home() / ".local" / "lib" / "debian-next-v3" / "periphx.py"
    return [sys.executable, str(fallback)] if fallback.is_file() else None


def periphx_cli_json(*arguments):
    command = periphx_cli_command()
    if not command:
        raise RuntimeError("CLI PeriphX introuvable")
    result = subprocess.run(
        [*command, *arguments], capture_output=True, text=True,
        timeout=8, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "opération pilote refusée")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("réponse CLI PeriphX invalide") from error


def driver_cli_json(*arguments):
    return periphx_cli_json("drivers", *arguments)


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


def device_groups(daemon_devices=NO_DAEMON_CHECK):
    if daemon_devices is NO_DAEMON_CHECK:
        daemon_groups = daemon_device_groups()
    elif daemon_devices is None:
        daemon_groups = None
    else:
        daemon_groups = daemon_device_groups(daemon_devices)
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
        ("Profils", "PeriphX local", "JSON isolé"),
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
        self.test_devices = []
        self.test_devices_signature = None
        self.test_stop_event = threading.Event()
        self.test_running = False
        self.test_generation = 0
        self.test_log_lines = []
        self.test_previous_keys = set()
        self.test_expected_controls = set()
        self.test_tested_controls = set()
        self.test_session_id = None
        self.test_control_widgets = {}
        self.test_controls = []
        self.connect("close-request", self.close_requested)

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
        self.stack.add_titled(self.build_input_test(), "input-test", "Test des touches")
        self.stack.add_titled(self.build_drivers(), "drivers", "Pilotes")
        self.stack.add_titled(self.build_display_link(), "display", "Affichage")
        self.stack.add_titled(self.build_capabilities(), "capabilities", "Capacités")
        switcher = Gtk.StackSwitcher(stack=self.stack)
        header.set_title_widget(switcher)
        toolbar.set_content(self.stack)
        self.set_content(toolbar)
        self.last_groups_signature = None
        self.refresh()
        self.refresh_timer_id = GLib.timeout_add_seconds(2, self.refresh_devices)

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
            "PeriphX utilise les interfaces Debian standard et n’envoie aucune commande "
            "USB sans backend identifié.",
        ))
        self.capability_rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                           spacing=0, css_classes=["boxed-list"])
        self.capability_content.append(self.capability_rows_box)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self.capability_content)
        return scroll

    def build_input_test(self):
        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=16,
            margin_top=24, margin_bottom=24, margin_start=28, margin_end=28,
        )
        content.append(self.section(
            "Test des touches en temps réel",
            "Observez les entrées du clavier, de la souris ou de la manette sélectionnée. "
            "Aucune commande n’est envoyée au périphérique.",
        ))

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.test_selector = Gtk.DropDown.new_from_strings(["Aucun périphérique externe"])
        self.test_selector.set_hexpand(True)
        self.test_selector.set_sensitive(False)
        self.test_selector.connect("notify::selected", self.test_selection_changed)
        controls.append(self.test_selector)
        self.test_toggle = Gtk.Button(
            label="Démarrer", css_classes=["suggested-action"], sensitive=False,
        )
        self.test_toggle.connect("clicked", self.toggle_input_test)
        controls.append(self.test_toggle)
        clear_button = Gtk.Button(label="Effacer")
        clear_button.connect("clicked", self.clear_input_test)
        controls.append(clear_button)
        content.append(controls)

        self.test_status = Gtk.Label(
            label="Sélectionnez un périphérique externe.", xalign=0, wrap=True,
            css_classes=["dim-label"],
        )
        content.append(self.test_status)
        visual_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        visual_header.append(Gtk.Label(
            label="Visualiseur matériel", xalign=0, hexpand=True,
            css_classes=["title-2"],
        ))
        self.test_visual_count = Gtk.Label(label="", css_classes=["dim-label"])
        visual_header.append(self.test_visual_count)
        content.append(visual_header)
        self.test_visual = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
            column_spacing=8, row_spacing=8,
            min_children_per_line=4, max_children_per_line=12,
        )
        visual_scroll = Gtk.ScrolledWindow(min_content_height=170)
        visual_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        visual_scroll.set_child(self.test_visual)
        content.append(visual_scroll)
        activity = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8,
            margin_top=16, margin_bottom=16, margin_start=16, margin_end=16,
            css_classes=["boxed-list"],
        )
        self.test_activity_title = Gtk.Label(
            label="En attente d’une entrée", xalign=0, css_classes=["title-2"],
        )
        self.test_activity_value = Gtk.Label(
            label="—", xalign=0, wrap=True, selectable=True,
        )
        self.test_activity_bar = Gtk.ProgressBar(show_text=False)
        activity.append(self.test_activity_title)
        activity.append(self.test_activity_value)
        activity.append(self.test_activity_bar)
        self.test_coverage_label = Gtk.Label(
            label="Aucun contrôle testé", xalign=0, css_classes=["dim-label"],
        )
        activity.append(self.test_coverage_label)
        content.append(activity)

        content.append(self.section(
            "Journal", "Les 60 événements les plus récents sont conservés à l’écran.",
        ))
        self.test_log_label = Gtk.Label(
            label="Aucun événement", xalign=0, yalign=0, wrap=True,
            selectable=True, css_classes=["monospace", "dim-label"],
        )
        log_scroll = Gtk.ScrolledWindow(vexpand=True, min_content_height=180)
        log_scroll.set_child(self.test_log_label)
        content.append(log_scroll)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(content)
        return scroll

    def build_drivers(self):
        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=14,
            margin_top=24, margin_bottom=24, margin_start=28, margin_end=28,
        )
        content.append(self.section(
            "Pilotes personnalisés",
            "Installe ou met à jour des manifests stricts. Les capacités d’écriture "
            "restent refusées tant qu’un protocole matériel n’est pas validé.",
        ))
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        install_button = Gtk.Button(label="Installer un manifest", css_classes=["suggested-action"])
        install_button.connect("clicked", self.choose_driver_manifest, "install")
        update_button = Gtk.Button(label="Mettre à jour un pilote")
        update_button.connect("clicked", self.choose_driver_manifest, "update")
        refresh_button = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Actualiser")
        refresh_button.connect("clicked", lambda _button: self.refresh_driver_manifests())
        actions.append(install_button)
        actions.append(update_button)
        actions.append(refresh_button)
        content.append(actions)
        self.driver_status = Gtk.Label(label="", xalign=0, wrap=True, css_classes=["dim-label"])
        content.append(self.driver_status)
        self.driver_rows = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=0, css_classes=["boxed-list"],
        )
        content.append(self.driver_rows)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(content)
        GLib.idle_add(self.refresh_driver_manifests)
        return scroll

    def choose_driver_manifest(self, _button, action):
        chooser = Gtk.FileChooserNative(
            title="Choisir un manifest de pilote PeriphX",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
            accept_label="Sélectionner",
            cancel_label="Annuler",
        )
        file_filter = Gtk.FileFilter(name="Manifest JSON")
        file_filter.add_pattern("*.json")
        chooser.add_filter(file_filter)
        chooser.connect("response", self.driver_manifest_chosen, action)
        chooser.show()

    def driver_manifest_chosen(self, chooser, response, action):
        if response != Gtk.ResponseType.ACCEPT:
            return
        selected = chooser.get_file()
        manifest = selected.get_path() if selected else None
        if not manifest:
            self.driver_status.set_text("Le manifest doit être un fichier local.")
            return
        try:
            result = driver_cli_json(action, manifest)
            reloaded = "daemon rechargé" if result.get("daemon_reloaded") else "daemon hors ligne"
            self.driver_status.set_text(f"Pilote {action} réussi · {reloaded} · lecture seule")
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            self.driver_status.set_text(f"Échec du pilote : {error}")
        self.refresh_driver_manifests()

    def refresh_driver_manifests(self):
        if not hasattr(self, "driver_rows"):
            return False
        self.clear(self.driver_rows)
        try:
            manifests = driver_cli_json("list")
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            self.driver_status.set_text(str(error))
            manifests = []
        if not manifests:
            self.driver_rows.append(self.detail_row(
                "Aucun pilote custom", "Les pilotes génériques restent en lecture seule.",
                "security-high-symbolic",
            ))
        for manifest in manifests:
            name = manifest.get("name") or Path(manifest.get("path", "manifest")).name
            state = f"Version {manifest.get('version')} · lecture seule" if manifest.get("valid") \
                else f"Invalide · {manifest.get('error', 'erreur inconnue')}"
            icon = "emblem-ok-symbolic" if manifest.get("valid") else "dialog-warning-symbolic"
            self.driver_rows.append(self.detail_row(name, state, icon))
        return False

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

        hid_interfaces = device.get("hid_interfaces") or []
        if hid_interfaces:
            self.device_detail_content.append(self.section(
                "Interfaces HID", "Sélectionnez l’interface physique à observer.",
            ))
            interface_rows = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL, spacing=0, css_classes=["boxed-list"],
            )
            for hid_interface in hid_interfaces:
                row = Gtk.Box(
                    orientation=Gtk.Orientation.HORIZONTAL, spacing=12,
                    margin_top=10, margin_bottom=10, margin_start=12, margin_end=12,
                )
                summary = " · ".join(filter(None, (
                    hid_interface.get("role"),
                    hid_interface.get("interface_number"),
                    ", ".join(hid_interface.get("nodes") or []),
                )))
                labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
                labels.append(Gtk.Label(
                    label=hid_interface.get("name") or hid_interface.get("id") or "Interface HID",
                    xalign=0,
                ))
                labels.append(Gtk.Label(label=summary or "Lecture seule", xalign=0, wrap=True,
                                        css_classes=["dim-label"]))
                row.append(labels)
                capture = Gtk.Button(label="Capturer 1 s")
                interface_id = str(hid_interface.get("id") or "")
                capture.set_sensitive(bool(device.get("id") and interface_id))
                capture.connect(
                    "clicked", self.capture_hid_interface,
                    device.get("id"), interface_id,
                )
                row.append(capture)
                interface_rows.append(row)
            self.device_detail_content.append(interface_rows)
            self.capture_status = Gtk.Label(
                label="Aucune capture · entrée uniquement", xalign=0, wrap=True,
                selectable=True, css_classes=["dim-label"],
            )
            self.device_detail_content.append(self.capture_status)

    def capture_hid_interface(self, button, device_id, interface_id):
        button.set_sensitive(False)
        self.capture_status.set_text("Capture en cours pendant 1 seconde…")

        def worker():
            try:
                result = periphx_cli_json(
                    "capture", device_id, "--interface", interface_id,
                    "--duration-ms", "1000", "--max-reports", "16", "--json",
                )
                GLib.idle_add(self.capture_hid_finished, button, result, None)
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                GLib.idle_add(self.capture_hid_finished, button, None, str(error))

        threading.Thread(target=worker, daemon=True).start()

    def capture_hid_finished(self, button, result, error):
        if error:
            self.capture_status.set_text(f"Capture indisponible : {error}")
        else:
            reports = result.get("reports") or []
            if reports:
                lines = [
                    f"{report.get('node', 'hidraw')} · {report.get('raw_hex', '')[:96]}"
                    for report in reports[-8:]
                ]
                self.capture_status.set_text("\n".join(lines))
            else:
                self.capture_status.set_text("Aucun report reçu pendant 1 seconde · lecture seule")
        button.set_sensitive(True)
        return False

    def close_requested(self, _window):
        self.stop_input_test()
        return False

    def selected_test_device(self):
        index = self.test_selector.get_selected()
        return self.test_devices[index] if index < len(self.test_devices) else None

    def refresh_test_devices(self, devices):
        candidates = []
        seen = set()
        for device in devices or []:
            identifier = device.get("id")
            device_class = device.get("class")
            classes = device.get("classes") or [device_class]
            if device_class not in MANAGED_DEVICE_CLASSES:
                device_class = next(
                    (item for item in MANAGED_DEVICE_CLASSES if item in classes), device_class
                )
            if (not identifier or identifier in seen or not is_external_peripheral(device)
                    or device_class not in MANAGED_DEVICE_CLASSES):
                continue
            item = dict(device)
            item["class"] = device_class
            candidates.append(item)
            seen.add(identifier)
        signature = tuple(
            (item["id"], item.get("name"), item.get("class")) for item in candidates
        )
        if signature == self.test_devices_signature:
            return
        previous = self.selected_test_device()
        previous_id = previous.get("id") if previous else None
        self.stop_input_test()
        self.test_devices = candidates
        self.test_devices_signature = signature
        labels = [
            f"{item.get('name', 'Périphérique')} · {item.get('class', 'HID')} · "
            f"{item.get('connection', 'connexion inconnue')}"
            for item in candidates
        ] or ["Aucun clavier, souris ou manette externe"]
        self.test_selector.set_model(Gtk.StringList.new(labels))
        selected = next(
            (index for index, item in enumerate(candidates) if item["id"] == previous_id), 0
        )
        self.test_selector.set_selected(selected)
        available = bool(candidates)
        self.test_selector.set_sensitive(available)
        self.test_toggle.set_sensitive(available)
        self.test_status.set_text(
            "Prêt · événements Linux entrants uniquement" if available
            else "Aucun périphérique externe testable n’est connecté."
        )

    def test_selection_changed(self, _selector, _property):
        if self.test_running:
            self.stop_input_test("Périphérique de test modifié.")
        device = self.selected_test_device()
        self.test_controls = []
        self.test_expected_controls.clear()
        self.test_tested_controls.clear()
        self.clear(self.test_visual)
        self.test_control_widgets.clear()
        self.test_visual_count.set_text("")
        if device:
            self.test_activity_title.set_text(device.get("name", "Périphérique"))
            self.test_activity_value.set_text("Appuyez sur Démarrer, puis utilisez le périphérique.")

    def toggle_input_test(self, _button):
        if self.test_running:
            self.stop_input_test("Test arrêté.")
            return
        device = self.selected_test_device()
        if not device:
            return
        self.test_running = True
        self.test_generation += 1
        generation = self.test_generation
        self.test_stop_event = threading.Event()
        self.test_previous_keys = set()
        self.test_expected_controls.clear()
        self.test_tested_controls.clear()
        if self.test_controls:
            self.render_test_controls(self.test_controls)
        self.test_coverage_label.set_text("Découverte des contrôles…")
        self.test_activity_bar.set_fraction(0)
        self.test_session_id = f"gui-input-{os.getpid()}-{generation}"
        session_id = self.test_session_id
        self.test_toggle.set_label("Arrêter")
        self.test_toggle.remove_css_class("suggested-action")
        self.test_toggle.add_css_class("destructive-action")
        self.test_status.set_text("Test actif · entrée uniquement · aucune commande envoyée")
        self.test_activity_title.set_text(device.get("name", "Périphérique"))

        def worker():
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(0.3)
                    client.connect(pericored_socket_path())
                    client.sendall((json.dumps({
                        "method": "start_input_test",
                        "request_id": session_id,
                        "params": {"device_id": device["id"]},
                    }) + "\n").encode())
                    buffer = b""
                    started = False
                    while not self.test_stop_event.is_set():
                        try:
                            chunk = client.recv(65536)
                        except socket.timeout:
                            continue
                        if not chunk:
                            break
                        buffer += chunk
                        lines = buffer.split(b"\n")
                        buffer = lines.pop()
                        events = []
                        for line in lines:
                            if not line:
                                continue
                            payload = json.loads(line)
                            if not started:
                                if not payload.get("ok"):
                                    detail = (payload.get("error") or {}).get(
                                        "message", "session refusée",
                                    )
                                    raise RuntimeError(detail)
                                started = True
                                GLib.idle_add(
                                    self.input_test_batch, generation, device,
                                    {"started": payload.get("result") or {}}, None,
                                )
                            elif payload.get("event") == "input":
                                events.append(payload)
                        if events:
                            GLib.idle_add(
                                self.input_test_batch, generation, device,
                                {"events": events}, None,
                            )
            except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
                GLib.idle_add(
                    self.input_test_batch, generation, device, None, str(error),
                )

        threading.Thread(target=worker, daemon=True).start()

    def stop_input_test(self, message=None):
        if not hasattr(self, "test_toggle"):
            return
        self.test_stop_event.set()
        session_id = self.test_session_id
        self.test_session_id = None
        if session_id:
            threading.Thread(
                target=self.stop_daemon_input_session,
                args=(session_id,), daemon=True,
            ).start()
        self.test_generation += 1
        self.test_running = False
        self.test_toggle.set_label("Démarrer")
        self.test_toggle.remove_css_class("destructive-action")
        self.test_toggle.add_css_class("suggested-action")
        self.test_activity_bar.set_fraction(0)
        if message:
            self.test_status.set_text(message)

    @staticmethod
    def stop_daemon_input_session(session_id):
        try:
            pericored_request(
                "stop_input_test", {"session_id": session_id},
                request_id=f"stop-{session_id}",
            )
        except (OSError, RuntimeError, json.JSONDecodeError):
            pass

    def clear_input_test(self, _button=None):
        self.test_log_lines.clear()
        self.test_previous_keys.clear()
        self.test_tested_controls.clear()
        if self.test_controls:
            self.render_test_controls(self.test_controls)
        self.test_log_label.set_text("Aucun événement")
        self.test_activity_value.set_text("—")
        self.test_activity_bar.set_fraction(0)
        total = len(self.test_expected_controls)
        self.test_coverage_label.set_text(
            f"0 / {total} contrôles testés" if total else "Aucun contrôle testé"
        )

    def append_test_event(self, text):
        self.test_log_lines.append(f"{time.strftime('%H:%M:%S')}  {text}")
        self.test_log_lines = self.test_log_lines[-60:]
        self.test_log_label.set_text("\n".join(reversed(self.test_log_lines)))

    def render_test_controls(self, controls):
        self.clear(self.test_visual)
        self.test_control_widgets.clear()
        for item in controls:
            control = item.get("control")
            if not control:
                continue
            label = control.rsplit(".", 1)[-1].replace("_", " ").title()
            card = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL, spacing=5,
                margin_top=7, margin_bottom=7, margin_start=9, margin_end=9,
                css_classes=["card"],
            )
            title = Gtk.Label(label=label, ellipsize=3, max_width_chars=16)
            card.append(title)
            if item.get("kind") in ("axis", "hat", "touch"):
                value = Gtk.Label(label="0.000", css_classes=["dim-label"])
                level = Gtk.LevelBar()
                level.set_min_value(0)
                level.set_max_value(1)
                level.set_value(0 if ".trigger." in control else 0.5)
                level.set_size_request(100, -1)
                card.append(value)
                card.append(level)
                self.test_control_widgets[control] = ("axis", title, value, level)
            else:
                state = Gtk.Label(label="○ Non testé", css_classes=["dim-label"])
                card.append(state)
                self.test_control_widgets[control] = ("button", title, state)
            self.test_visual.append(card)
        self.test_visual_count.set_text(f"{len(controls)} contrôle(s)")

    def update_test_control(self, event):
        control = event.get("control")
        widget = self.test_control_widgets.get(control)
        if not widget:
            return
        raw = int(event.get("raw_value") or 0)
        if widget[0] == "button":
            state = widget[2]
            state.set_text("● Pressé" if raw else "✓ Détecté")
            state.remove_css_class("dim-label")
            state.add_css_class("success")
        else:
            normalized = event.get("normalized_value")
            value = float(normalized) if normalized is not None else 0.0
            widget[2].set_text(f"{value:+.3f}")
            fraction = value if ".trigger." in control else (value + 1) / 2
            widget[3].set_value(max(0, min(1, fraction)))

    def input_test_batch(self, generation, device, result, error):
        if generation != self.test_generation or not self.test_running:
            return False
        if error:
            self.stop_input_test(f"Test indisponible : {error}")
            return False
        started = (result or {}).get("started")
        if started is not None:
            controls = (started.get("capabilities") or {}).get("controls") or []
            self.test_controls = controls
            self.render_test_controls(controls)
            self.test_expected_controls = {
                item.get("control") for item in controls
                if item.get("kind") in ("key", "button") and item.get("control")
            }
            total = len(self.test_expected_controls)
            self.test_coverage_label.set_text(
                f"0 / {total} boutons ou touches testés" if total
                else f"{len(controls)} contrôle(s) analogique(s) détecté(s)"
            )
            self.test_status.set_text(
                f"Session pericored active · {len(controls)} contrôle(s) · lecture seule"
            )
        events = (result or {}).get("events") or []
        for event in events:
            summary = normalized_event_text(event)
            if not summary:
                continue
            self.test_activity_value.set_text(summary)
            self.append_test_event(summary)
            self.update_test_control(event)
            if event.get("kind") in ("key", "button") and event.get("raw_value") == 1:
                self.test_tested_controls.add(event.get("control"))
            if self.test_expected_controls:
                tested = len(self.test_tested_controls & self.test_expected_controls)
                total = len(self.test_expected_controls)
                self.test_activity_bar.set_fraction(tested / total)
                self.test_coverage_label.set_text(
                    f"{tested} / {total} boutons ou touches testés"
                    + (" · Tous détectés ✓" if tested == total else "")
                )
            else:
                self.test_activity_bar.pulse()
        reports = (result or {}).get("reports") or []
        for report in reports:
            summary = summarize_hid_report(device.get("class"), report)
            self.test_activity_value.set_text(summary)
            if device.get("class") == "keyboard":
                keys = keyboard_report_keys(report)
                for key in sorted(keys - self.test_previous_keys):
                    self.append_test_event(f"Touche pressée · {key}")
                for key in sorted(self.test_previous_keys - keys):
                    self.append_test_event(f"Touche relâchée · {key}")
                self.test_previous_keys = keys
            else:
                self.append_test_event(summary)
            self.test_activity_bar.pulse()
        if events or reports:
            self.test_status.set_text(
                f"Test actif · {len(self.test_log_lines)} événement(s) affiché(s) · lecture seule"
            )
        return False

    def refresh(self):
        daemon_devices = pericored_inventory()
        self.refresh_test_devices(daemon_devices)
        groups = device_groups(daemon_devices)
        total = sum(len(items) for _title, _subtitle, items, _kind in groups)
        source = "pericored" if daemon_devices is not None else "détection locale"
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
