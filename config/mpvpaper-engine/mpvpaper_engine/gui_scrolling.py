"""Keep form scrolling native, without changing values under the pointer."""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


def allow_page_scroll(widget):
    """Disable only wheel adjustment; dragging, clicks and keyboard stay active."""
    if isinstance(widget, (Gtk.Range, Gtk.SpinButton)):
        controllers = widget.observe_controllers()
        for index in range(controllers.get_n_items()):
            controller = controllers.get_item(index)
            if isinstance(controller, Gtk.EventControllerScroll):
                controller.set_propagation_phase(Gtk.PropagationPhase.NONE)
    return widget


def scrolled_window(**properties):
    properties.setdefault("vexpand", True)
    properties.setdefault("hscrollbar_policy", Gtk.PolicyType.NEVER)
    properties.setdefault("vscrollbar_policy", Gtk.PolicyType.AUTOMATIC)
    properties.setdefault("overlay_scrolling", False)
    properties.setdefault("kinetic_scrolling", True)
    window = Gtk.ScrolledWindow(**properties)
    window.add_css_class("engine-scroll")
    return window
