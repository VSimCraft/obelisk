"""Reusable GTK helpers and widgets: background Worker, confirm dialog, setting Control."""

from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from . import settings

if TYPE_CHECKING:
    from .gui import MainWindow

DEBOUNCE_MS = 150


class Worker:
    """Single worker thread; results are marshalled back via GLib.idle_add."""

    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._loop, name="obelisk-worker", daemon=True)
        self._thread.start()

    def run(self, fn, callback):
        """Run fn() on the worker; callback(result, exception) on the GTK thread."""
        self._queue.put((fn, callback))

    def stop(self):
        self._queue.put(None)

    def _loop(self):
        while True:
            item = self._queue.get()
            if item is None:
                return
            fn, callback = item
            try:
                result, error = fn(), None
            except Exception as exc:  # noqa: BLE001 - reported to the GUI
                result, error = None, exc
            GLib.idle_add(self._deliver, callback, result, error)

    @staticmethod
    def _deliver(callback, result, error):
        callback(result, error)
        return GLib.SOURCE_REMOVE


def _configure_dialog(dialog, confirm_label, appearance):
    dialog.add_response("cancel", "Cancel")
    dialog.add_response("confirm", confirm_label)
    dialog.set_response_appearance("confirm", appearance)
    dialog.set_default_response("cancel")
    dialog.set_close_response("cancel")


def confirm(parent, heading, body, confirm_label, on_confirm, *, on_cancel=None, destructive=False):
    """Modal confirmation. Uses Adw.AlertDialog when available, else MessageDialog."""
    appearance = (
        Adw.ResponseAppearance.DESTRUCTIVE if destructive else Adw.ResponseAppearance.SUGGESTED
    )

    def finish(confirmed):
        if confirmed:
            on_confirm()
        elif on_cancel is not None:
            on_cancel()

    if hasattr(Adw, "AlertDialog"):
        dialog = Adw.AlertDialog(heading=heading, body=body)
        _configure_dialog(dialog, confirm_label, appearance)

        def on_done(dlg, result):
            finish(dlg.choose_finish(result) == "confirm")

        dialog.choose(parent, None, on_done)
    else:
        dialog = Adw.MessageDialog(transient_for=parent, modal=True, heading=heading, body=body)
        _configure_dialog(dialog, confirm_label, appearance)
        dialog.connect("response", lambda _d, response: finish(response == "confirm"))
        dialog.present()


class Control:
    """One int setting as an Adw.SpinRow + Gtk.Scale, with debounced change reporting."""

    def __init__(self, window: MainWindow, setting: settings.Setting):
        self.window = window
        self.setting = setting
        self._silent = False
        self._timer = 0
        step = max(1, setting.step)
        initial = max(setting.min, min(setting.max, setting.default))
        self.adjustment = Gtk.Adjustment(
            value=initial,
            lower=setting.min,
            upper=setting.max,
            step_increment=step,
            page_increment=step * 10,
        )
        subtitle = f"{setting.min} - {setting.max} {setting.unit}".strip()
        self.row = Adw.SpinRow(
            title=GLib.markup_escape_text(setting.label),
            subtitle=subtitle,
            adjustment=self.adjustment,
            digits=0,
        )
        scale = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=self.adjustment,
            draw_value=False,
            hexpand=True,
            valign=Gtk.Align.CENTER,
        )
        scale.set_size_request(220, -1)
        self.row.add_suffix(scale)
        self.adjustment.connect("value-changed", self._on_changed)

    def get_value(self) -> int:
        return round(self.adjustment.get_value())

    def set_value(self, value: int):
        """Update the widget without scheduling a write."""
        s = self.setting
        self._cancel_timer()
        self._silent = True
        try:
            self.adjustment.set_value(max(s.min, min(s.max, value)))
        finally:
            self._silent = False

    def set_enabled(self, enabled: bool):
        self.row.set_sensitive(enabled)

    def _cancel_timer(self):
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def _on_changed(self, *_args):
        if self._silent:
            return
        self._cancel_timer()
        self._timer = GLib.timeout_add(DEBOUNCE_MS, self._fire)

    def _fire(self):
        self._timer = 0
        self.window.request_change(self, self.get_value())
        return GLib.SOURCE_REMOVE
