"""GTK3 layer-shell HUD worker. GTK4 remains isolated in the editor process."""

import json
import os
from pathlib import Path
import sys
import time

from .hud import preview_settings, _palette, settings_from_config
from .hud_scene import draw, geometry, logical_screen
from .hud_positioning import Rect
from .hud_layers import detect_layers, panel_rects, HudLayerError
from .monitors import detect_monitors, MonitorError


def main():
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gtk, Gdk, GLib, GtkLayerShell
    import cairo

    if not Gtk.init_check()[0] or not GtkLayerShell.is_supported():
        print("Desktop HUD: Wayland layer-shell indisponible.", file=sys.stderr)
        return 1
    state_file, config_home = Path(sys.argv[1]), Path(sys.argv[2])
    parent_pid = int(sys.argv[3])
    display = Gdk.Display.get_default()
    windows = {}
    payload = {}
    stamp = None
    last_discovery = 0
    monitors, layers = [], []
    last_frame = None

    def create_window(monitor):
        window = Gtk.Window()
        window.set_title("MPVpaper Desktop HUD")
        window.set_app_paintable(True)
        window.set_visual(window.get_screen().get_rgba_visual())
        GtkLayerShell.init_for_window(window)
        GtkLayerShell.set_namespace(window, "mpvpaper-desktop-hud")
        GtkLayerShell.set_layer(window, GtkLayerShell.Layer.BOTTOM)
        GtkLayerShell.set_monitor(window, monitor)
        GtkLayerShell.set_keyboard_mode(window, GtkLayerShell.KeyboardMode.NONE)
        GtkLayerShell.set_exclusive_zone(window, -1)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(window, edge, True)
        window.connect("realize", lambda widget: widget.get_window().input_shape_combine_region(
            cairo.Region(), 0, 0))

        def paint(widget, context):
            context.set_operator(cairo.OPERATOR_SOURCE)
            context.set_source_rgba(0, 0, 0, 0)
            context.paint()
            context.set_operator(cairo.OPERATOR_OVER)
            data, screen, panels, palette = widget.hud_frame
            layout = geometry(data, screen, panels)
            rect = layout["rect"]
            draw(context, data, Rect(rect.x - screen.x, rect.y - screen.y,
                                     rect.width, rect.height), palette)
            return True

        window.connect("draw", paint)
        return window

    def tick():
        nonlocal payload, stamp, monitors, layers, last_discovery, last_frame
        if os.getppid() != parent_pid:
            Gtk.main_quit()
            return False
        try:
            current_stamp = state_file.stat().st_mtime_ns
            if current_stamp != stamp:
                payload = json.loads(state_file.read_text(encoding="utf-8"))
                stamp = current_stamp
        except (OSError, ValueError):
            return True
        if time.monotonic() - last_discovery >= 2:
            try:
                monitors = detect_monitors()
            except MonitorError:
                pass
            try:
                layers = detect_layers()
            except HudLayerError:
                layers = []
            last_discovery = time.monotonic()
        palette = _palette(config_home.parent / "waybar" / "panel-colors.css")
        frame = (stamp, int(time.time() // 60), repr(monitors), repr(layers), repr(palette))
        if frame == last_frame:
            return True
        last_frame = frame
        active = set()
        for monitor in monitors:
            if not monitor.width or not monitor.height:
                continue
            previews = payload.get("previews", {})
            data = preview_settings(payload.get("settings", {}), monitor.name, previews)
            if not settings_from_config(data).enabled:
                continue
            screen = logical_screen(monitor)
            gdk_monitor = next((display.get_monitor(index) for index in range(display.get_n_monitors())
                                if display.get_monitor(index).get_geometry().x == screen.x
                                and display.get_monitor(index).get_geometry().y == screen.y), None)
            if gdk_monitor is None:
                continue
            active.add(monitor.name)
            window = windows.get(monitor.name)
            if window is None:
                window = windows[monitor.name] = create_window(gdk_monitor)
            else:
                GtkLayerShell.set_monitor(window, gdk_monitor)
            window.hud_frame = (data, screen, panel_rects(layers, monitor.name), palette)
            window.show_all()
            window.queue_draw()
        for name in set(windows) - active:
            windows.pop(name).destroy()
        return True

    tick()
    GLib.timeout_add(250, tick)
    Gtk.main()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ImportError, ValueError) as error:
        print(f"Desktop HUD: {error}. Installer gir1.2-gtklayershell-0.1 et python3-gi-cairo.",
              file=sys.stderr)
        raise SystemExit(1)
