#!/usr/bin/env python3

import json
import os
import signal
import subprocess
import tempfile
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk


def command(*args):
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=2, check=False
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


class MediaPanel(Gtk.Window):
    def __init__(self):
        GLib.set_prgname("deblestia-bar-media")
        super().__init__(title="Centre multimédia")
        self.set_default_size(520, 410)
        self.set_resizable(False)
        self.set_border_width(18)
        self.connect("destroy", self.on_destroy)

        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.set_app_paintable(True)

        css = Gtk.CssProvider()
        css.load_from_data(b"""
            window { background-color: rgba(14,15,22,0.94); color: #f3edf2; }
            label { color: #f3edf2; }
            .title { font-size: 21px; font-weight: 700; color: #ff708f; }
            .artist { font-size: 14px; color: #b8aeb8; }
            .source { color: #e23864; }
            button, combobox, scale {
                background: rgba(255,255,255,0.07);
                color: #f3edf2;
                border: 1px solid rgba(226,56,100,0.48);
                border-radius: 10px;
                padding: 8px;
            }
            button:hover { background: rgba(226,56,100,0.25); }
            trough { background: rgba(255,255,255,0.10); border-radius: 8px; }
            highlight { background: #e23864; border-radius: 8px; }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(root)

        self.title_label = Gtk.Label(label="Aucune lecture", xalign=0)
        self.title_label.get_style_context().add_class("title")
        self.artist_label = Gtk.Label(label="", xalign=0)
        self.artist_label.get_style_context().add_class("artist")
        self.source_label = Gtk.Label(label="Source : —", xalign=0)
        self.source_label.get_style_context().add_class("source")
        root.pack_start(self.title_label, False, False, 0)
        root.pack_start(self.artist_label, False, False, 0)
        root.pack_start(self.source_label, False, False, 0)

        controls = Gtk.Box(spacing=10, homogeneous=True)
        for icon, action in (("", "previous"), ("  /  ", "play-pause"), ("", "next")):
            button = Gtk.Button(label=icon)
            button.connect("clicked", lambda _button, name=action: command("playerctl", name))
            controls.pack_start(button, True, True, 0)
        root.pack_start(controls, False, False, 0)

        audio_row = Gtk.Box(spacing=10)
        audio_row.pack_start(Gtk.Label(label="  Sortie", xalign=0), False, False, 0)
        self.sink_combo = Gtk.ComboBoxText()
        self.sink_combo.connect("changed", self.change_sink)
        audio_row.pack_start(self.sink_combo, True, True, 0)
        root.pack_start(audio_row, False, False, 0)

        volume_row = Gtk.Box(spacing=10)
        self.volume_label = Gtk.Label(label="Volume 0 %")
        self.volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.volume.set_draw_value(False)
        self.volume.connect("value-changed", self.change_volume)
        volume_row.pack_start(self.volume_label, False, False, 0)
        volume_row.pack_start(self.volume, True, True, 0)
        root.pack_start(volume_row, False, False, 0)

        self.wave = Gtk.DrawingArea()
        self.wave.set_size_request(-1, 135)
        self.wave.connect("draw", self.draw_wave)
        root.pack_start(self.wave, True, True, 0)
        self.bars = [0.04] * 32
        self.cava = None
        self.updating_volume = False

        self.refresh_sinks()
        self.refresh()
        self.start_cava()
        GLib.timeout_add_seconds(1, self.refresh)

    def refresh(self):
        title = command("playerctl", "metadata", "--format", "{{title}}")
        artist = command("playerctl", "metadata", "--format", "{{artist}}")
        player = command("playerctl", "metadata", "--format", "{{playerName}}")
        self.title_label.set_text(title or "Aucune lecture")
        self.artist_label.set_text(artist or "En attente d’un lecteur MPRIS")
        self.source_label.set_text(f"Source : {player or '—'}")

        volume_text = command("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@")
        try:
            value = float(volume_text.split()[1]) * 100
            self.updating_volume = True
            self.volume.set_value(value)
            self.volume_label.set_text(f"Volume {round(value)} %")
            self.updating_volume = False
        except (IndexError, ValueError):
            pass
        return True

    def refresh_sinks(self):
        output = command("pactl", "-f", "json", "list", "sinks")
        default = command("pactl", "get-default-sink")
        try:
            sinks = json.loads(output)
        except json.JSONDecodeError:
            sinks = []
        self.sink_combo.remove_all()
        active_index = 0
        for index, sink in enumerate(sinks):
            name = sink.get("name", "")
            description = sink.get("description", name)
            self.sink_combo.append(name, description)
            if name == default:
                active_index = index
        if sinks:
            self.sink_combo.set_active(active_index)

    def change_sink(self, combo):
        sink = combo.get_active_id()
        if sink:
            command("pactl", "set-default-sink", sink)

    def change_volume(self, scale):
        if self.updating_volume:
            return
        value = round(scale.get_value())
        self.volume_label.set_text(f"Volume {value} %")
        command("wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{value}%")

    def start_cava(self):
        config = tempfile.NamedTemporaryFile(mode="w", delete=False, prefix="cava-media-")
        config.write("""[general]\nframerate = 30\nbars = 32\n[input]\nmethod = pipewire\nsource = auto\n[output]\nmethod = raw\nraw_target = /dev/stdout\ndata_format = ascii\nascii_max_range = 1000\nchannels = mono\n""")
        config.close()
        self.cava_config = config.name
        try:
            self.cava = subprocess.Popen(
                ["cava", "-p", config.name], stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, bufsize=1
            )
            threading.Thread(target=self.read_cava, daemon=True).start()
        except OSError:
            self.cava = None

    def read_cava(self):
        if not self.cava or not self.cava.stdout:
            return
        for line in self.cava.stdout:
            try:
                values = [min(1.0, int(value) / 1000) for value in line.strip().split(";") if value]
            except ValueError:
                continue
            if values:
                GLib.idle_add(self.set_bars, values)

    def set_bars(self, values):
        self.bars = values[:32]
        self.wave.queue_draw()
        return False

    def draw_wave(self, _widget, context):
        allocation = self.wave.get_allocation()
        width, height = allocation.width, allocation.height
        gap = 3
        bar_width = max(2, (width - gap * len(self.bars)) / len(self.bars))
        context.set_source_rgba(0.89, 0.22, 0.39, 0.92)
        for index, value in enumerate(self.bars):
            bar_height = max(4, value * (height - 8))
            context.rectangle(index * (bar_width + gap), height - bar_height, bar_width, bar_height)
        context.fill()
        return False

    def on_destroy(self, *_args):
        if self.cava:
            self.cava.terminate()
        try:
            os.unlink(self.cava_config)
        except (AttributeError, OSError):
            pass
        Gtk.main_quit()


signal.signal(signal.SIGTERM, lambda *_args: Gtk.main_quit())
window = MediaPanel()
window.show_all()
Gtk.main()
