"""GTK4/libadwaita front-end for obelisk."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from . import center, hidraw, profiles, settings, wheels
from .device import Device
from .settings import MAX_TORQUE_KEY, Values
from .widgets import Control, Worker, confirm

APP_ID = "io.github.vsimcraft.obelisk"

CSS = """
.device-chip { padding: 4px 12px; border-radius: 999px; background: alpha(currentColor, 0.08); }
.device-chip.connected { background: alpha(@success_color, 0.16); }
.device-chip .status-dot { min-width: 8px; min-height: 8px; border-radius: 999px; background: alpha(currentColor, 0.4); }
.device-chip.connected .status-dot { background: @success_color; }
.device-chip.connected label { font-weight: 600; }
.save-button { background: @blue_3; color: white; padding: 6px 28px; font-weight: 600; }
.save-button:hover { background: @blue_2; }
.save-button:active { background: @blue_4; }
.save-button:disabled { background: alpha(@blue_3, 0.35); color: alpha(white, 0.6); }
.torque-value { font-size: 24px; font-weight: 700; }
"""

NO_WHEEL = "No wheelbase connected"
POLL_SECONDS = 2
ANGLE_POLL_MS = 200
ANGLE_TOAST_INTERVAL_S = 10
DEFAULT_STEERING_RANGE = 900

MAX_TORQUE_LABEL = "Max Torque Mode"
GAIN_KEY = "overall_gain"  # scales torque as a percentage of the wheel's maximum
ANGLE_IDLE = "—"
DEFAULT_PROFILE = "Default"

PROFILE_ERRORS = (profiles.ProfileError, OSError)
DEVICE_LOST_ERRORS = (OSError, hidraw.DeviceLost)


# --------------------------------------------------------------------------
# Main window
# --------------------------------------------------------------------------


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Obelisk", default_width=760, default_height=900)
        self.worker = Worker()
        self.fd: int | None = None
        self.device: Device | None = None
        self.path: str | None = None
        self.poll_id = 0
        self.controls: dict[str, Control] = {}
        self.values: Values = {}  # last known device values
        self.connected = False
        self.busy = False  # a center is running
        self.angle_poll_id = 0  # wheel-angle poll timer
        self._angle_pending = False  # a read_position is queued/running
        self._last_angle_toast = float("-inf")
        self.angle_row = None
        self.torque_row = None
        self.torque_value = None
        self.torque_switch = None
        self.wheel = None  # database entry of the connected wheelbase
        self.torque_on = False
        self.torque_known = False  # set by the active profile, a loaded profile, or a user flip
        self._torque_silent = False
        try:
            self.active_name: str | None = profiles.get_active()
        except PROFILE_ERRORS:
            self.active_name = None  # reported when the active profile is loaded on connect

        self._build_ui()
        self._set_state(False, NO_WHEEL)
        self.try_connect()
        GLib.timeout_add_seconds(POLL_SECONDS, self._watch)
        self.connect("close-request", self._on_close)

    # -- UI ------------------------------------------------------------------

    def _build_ui(self):
        self.toasts = Adw.ToastOverlay()
        toolbar = Adw.ToolbarView()
        self.toasts.set_child(toolbar)
        self.set_content(self.toasts)

        self.stack = Adw.ViewStack()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.ViewSwitcher(policy=Adw.ViewSwitcherPolicy.WIDE, stack=self.stack))

        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.state_dot = Gtk.Box(valign=Gtk.Align.CENTER)
        self.state_dot.add_css_class("status-dot")
        self.state_label = Gtk.Label(ellipsize=3, xalign=0, max_width_chars=40)
        self.state_box = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        self.state_box.add_css_class("device-chip")
        self.state_box.append(self.state_dot)
        self.state_box.append(self.state_label)
        header.pack_start(self.state_box)
        self.save_button = Gtk.Button(label="Save to profile", halign=Gtk.Align.CENTER, margin_top=10, margin_bottom=10)
        self.save_button.add_css_class("save-button")
        self.save_button.connect("clicked", lambda _b: self.request_save())
        toolbar.add_top_bar(header)
        toolbar.add_bottom_bar(self.save_button)

        self.stack.add_titled_with_icon(
            self._build_basic_page(), "basic", "Basic", "preferences-system-symbolic"
        )
        self.stack.add_titled_with_icon(
            self._build_profiles_page(), "profiles", "Profiles", "document-save-symbolic"
        )
        toolbar.set_content(self.stack)

    def _build_basic_page(self):
        items = [s for s in settings.REGISTRY if s.kind == "int"]
        if not items:
            return Adw.StatusPage(
                title="Basic",
                description="No settings available.",
                icon_name="dialog-information-symbolic",
            )
        page = Adw.PreferencesPage()
        angle_group = Adw.PreferencesGroup(title="Wheel angle")
        self.angle_row = Adw.ActionRow(title="Current angle", subtitle=ANGLE_IDLE)
        self.angle_row.add_css_class("property")
        self.center_button = Gtk.Button(label="Center", valign=Gtk.Align.CENTER)
        self.center_button.set_tooltip_text("Set the current wheel angle as center")
        self.center_button.connect("clicked", lambda _b: self.request_center())
        self.angle_row.add_suffix(self.center_button)
        angle_group.add(self.angle_row)
        page.add(angle_group)
        torque = Adw.PreferencesGroup(title="Torque")
        self.torque_row = Adw.PreferencesRow(activatable=False)
        self.torque_value = Gtk.Label(xalign=0, hexpand=True, valign=Gtk.Align.CENTER)
        self.torque_value.add_css_class("torque-value")
        self.torque_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        toggle = Gtk.Box(spacing=12, halign=Gtk.Align.END, hexpand=True)
        toggle.append(Gtk.Label(label=MAX_TORQUE_LABEL))
        toggle.append(self.torque_switch)
        halves = Gtk.Box(homogeneous=True, margin_top=14, margin_bottom=14, margin_start=16, margin_end=16)
        halves.append(self.torque_value)
        halves.append(toggle)
        self.torque_row.set_child(halves)
        self._refresh_torque_row()
        self.torque_switch.connect("notify::active", self._on_torque_toggled)
        torque.add(self.torque_row)
        page.add(torque)
        groups: dict[str, Adw.PreferencesGroup] = {}
        for s in items:
            group = groups.get(s.group)
            if group is None:
                group = groups[s.group] = Adw.PreferencesGroup(title=GLib.markup_escape_text(s.group))
                page.add(group)
            control = Control(self, s)
            self.controls[s.key] = control
            if s.key == GAIN_KEY:
                control.adjustment.connect("value-changed", lambda *_: self._refresh_torque_row())
            group.add(control.row)
        return page

    def _build_profiles_page(self):
        page = Adw.PreferencesPage()

        save_group = Adw.PreferencesGroup(title="Save current values")
        self.name_row = Adw.EntryRow(title="Save as", show_apply_button=True)
        self.name_row.connect("apply", self._on_save_as)
        save_group.add(self.name_row)
        page.add(save_group)

        self.profile_group = Adw.PreferencesGroup(title="Profiles")
        import_button = Gtk.Button(label="Import", valign=Gtk.Align.CENTER)
        import_button.connect("clicked", self._on_import)
        self.profile_group.set_header_suffix(import_button)
        page.add(self.profile_group)
        self._profile_rows: list[Adw.ActionRow] = []
        self._refresh_profiles()
        return page

    def _set_active(self, name):
        """Select (or with None clear) the profile applied on every connect."""
        try:
            profiles.set_active(name)
        except PROFILE_ERRORS as exc:
            self.toast(f"Cannot set active profile: {exc}")
            return False
        self.active_name = name
        self._refresh_profiles()
        return True

    def _update_save_tooltip(self):
        self.save_button.set_tooltip_text(
            f"Save the current values into the active profile “{self.active_name}”"
            if self.active_name
            else "Save the current values as the active profile “Default”"
        )

    def _make_profile_row(self, name):
        row = Adw.ActionRow(title=GLib.markup_escape_text(name))
        if name == self.active_name:
            row.set_subtitle("Active - applied on every connect")
            row.add_prefix(Gtk.Image.new_from_icon_name("object-select-symbolic"))
        for label, handler, css in (
            ("Load", self._on_load, "suggested-action"),
            ("Export", self._on_export, None),
            ("Delete", self._on_delete, "destructive-action"),
        ):
            button = Gtk.Button(label=label, valign=Gtk.Align.CENTER)
            if css:
                button.add_css_class(css)
            button.connect("clicked", lambda _b, h=handler, n=name: h(n))
            row.add_suffix(button)
        return row

    def _refresh_profiles(self):
        self._update_save_tooltip()
        for row in self._profile_rows:
            self.profile_group.remove(row)
        self._profile_rows = []
        try:
            names = profiles.list_profiles()
        except PROFILE_ERRORS as exc:
            self.toast(f"Cannot list profiles: {exc}")
            names = []
        if not names:
            row = Adw.ActionRow(title="No saved profiles")
            row.add_css_class("dim-label")
            self.profile_group.add(row)
            self._profile_rows.append(row)
            return
        for name in names:
            row = self._make_profile_row(name)
            self.profile_group.add(row)
            self._profile_rows.append(row)

    # -- feedback ------------------------------------------------------------

    def toast(self, message):
        self.toasts.add_toast(Adw.Toast.new(message))

    def _set_state(self, connected, text, tooltip=None):
        self.state_label.set_text(text)
        self.state_box.set_tooltip_text(tooltip or text)
        if connected:
            self.state_box.add_css_class("connected")
        else:
            self.state_box.remove_css_class("connected")
        self.connected = connected
        for control in self.controls.values():
            control.set_enabled(connected)
        self._update_actions()
        if not connected:
            self.wheel = None
        if self.torque_row is not None:
            self.torque_row.set_sensitive(connected)
        self._refresh_torque_row()
        if not connected:
            self._stop_angle_poll()
            self._show_angle(None)

    @property
    def can_act(self):
        """Connected and no device action running: center/save are allowed."""
        return self.connected and not self.busy

    def _update_actions(self):
        # connected is True only once read_all succeeded, i.e. controls hold device values
        enabled = self.can_act
        self.center_button.set_sensitive(enabled)
        self.save_button.set_sensitive(enabled)

    # -- connection ----------------------------------------------------------

    def try_connect(self):
        if self.device is not None:
            return
        try:
            path = hidraw.find_device()
            fd = hidraw.open_device(path)
        except hidraw.DeviceError as exc:
            self._set_state(False, NO_WHEEL, str(exc))
            self._start_polling()
            return
        self._stop_polling()
        device = Device(fd)
        self.fd, self.device, self.path = fd, device, path
        self._set_state(False, "Reading settings...")

        def read_device():
            values = device.read_all()
            with device._lock:
                try:
                    firmware = device.read_firmware()
                except hidraw.DeviceError:
                    firmware = None  # name is cosmetic; do not fail the connect over it
            return values, firmware

        def done(result, error):
            if self.device is not device:
                return  # superseded by a disconnect
            if error is not None:
                self.toast(f"Reading settings failed: {error}")
                self._close_device()
                self._set_state(False, NO_WHEEL, f"Read failed: {error}")
                return
            values, firmware = result
            for key, value in values.items():
                control = self.controls.get(key)
                if control is not None:
                    self.values[key] = value
                    control.set_value(value)
            wheel = wheels.lookup(hidraw.USB_ID)
            self.wheel = wheel
            name = wheel.name if wheel else hidraw.USB_ID
            details = [f"Firmware {firmware}"] if firmware else []
            if wheel:
                details.append(f"Max torque {wheel.max_torque_nm} Nm")
            self._set_state(True, name, "\n".join(details) or name)
            self._apply_active(device)

        self.worker.run(read_device, done)

    def _apply_active(self, device):
        """Silently apply the active profile (the wheelbase does not persist writes)."""
        try:
            active = profiles.load_active()
        except PROFILE_ERRORS as exc:
            self.toast(f"Active profile unreadable: {exc}")
            self._connect_ready(device)
            return
        if active is None:
            self._connect_ready(device)
            return
        name, values = active

        def done(written, error):
            if self.device is not device:
                return  # connection has since been replaced
            if error is not None:
                self.toast(f"Applying profile {name} failed: {error}")
                if isinstance(error, DEVICE_LOST_ERRORS):
                    self._disconnect(f"Disconnected: {error}")
                else:
                    self._connect_ready(device)
                return
            for key, value in written.items():
                control = self.controls.get(key)
                if control is not None:
                    self.values[key] = value
                    control.set_value(value)
            if MAX_TORQUE_KEY in values:  # already sent by apply_values; reflect it, send nothing
                self._set_torque(values[MAX_TORQUE_KEY])
            if written:
                self.toast(f"Applied profile {name} ({len(written)} changed)")
            self._connect_ready(device)

        self.worker.run(lambda: device.apply_values(values), done)

    def _connect_ready(self, device):
        """Connect sequence finished (values read, active profile applied): start polling the angle."""
        if self.device is not device:
            return
        self._start_angle_poll()

    # -- max torque ----------------------------------------------------------------

    def _refresh_torque_row(self):
        """Show self.torque_on and the resulting Nm without triggering a send."""
        if self.torque_switch is None:
            return
        self._torque_silent = True
        try:
            self.torque_switch.set_active(self.torque_on)
        finally:
            self._torque_silent = False
        gain = self.controls.get(GAIN_KEY)
        if self.wheel is None or not self.torque_known or gain is None:  # the wheelbase cannot report the mode
            self.torque_value.set_text(ANGLE_IDLE)
        else:
            nm = self.wheel.max_torque_nm * gain.get_value() / 100 * (1 if self.torque_on else 0.5)
            self.torque_value.set_text(f"{round(nm, 1):g} Nm")

    def _set_torque(self, on):
        self.torque_on, self.torque_known = bool(on), True
        self._refresh_torque_row()

    def _on_torque_toggled(self, row, _pspec):
        if self._torque_silent:
            return
        on = row.get_active()
        if on == self.torque_on:
            return  # echo of a programmatic revert, not a user flip
        device = self.device
        if device is None or not self.connected:
            self.toast("Not connected")
            self._refresh_torque_row()
            return
        if on:
            confirm(
                self,
                "Turn on Max Torque?",
                "The wheelbase will allow its full torque. Hold the wheel.",
                "Turn on",
                lambda: self._submit_torque(device, True),
                on_cancel=self._refresh_torque_row,
            )
        else:
            self._submit_torque(device, False)

    def _submit_torque(self, device, on):
        if self.device is not device:
            self._refresh_torque_row()
            self.toast("Not connected")
            return

        def done(_result, error):
            if error is None:
                self._set_torque(on)
                self.toast(f"Max Torque {'on' if on else 'off'}")
                return
            self._refresh_torque_row()  # back to what was last sent
            if self.device is not device:
                return  # error from a connection that has since been replaced
            self.toast(f"Max Torque failed: {error}")
            if isinstance(error, DEVICE_LOST_ERRORS):
                self._disconnect(f"Disconnected: {error}")

        self.worker.run(lambda: device.set_max_torque(on), done)

    # -- wheel angle -------------------------------------------------------------

    def _start_angle_poll(self):
        if not self.angle_poll_id:
            self.angle_poll_id = GLib.timeout_add(ANGLE_POLL_MS, self._angle_tick)

    def _stop_angle_poll(self):
        if self.angle_poll_id:
            GLib.source_remove(self.angle_poll_id)
            self.angle_poll_id = 0

    def _angle_tick(self):
        device = self.device
        if device is None or not self.connected:
            self.angle_poll_id = 0
            return GLib.SOURCE_REMOVE
        if self.busy or self._angle_pending:
            return GLib.SOURCE_CONTINUE
        self._angle_pending = True

        def done(counts, error):
            self._angle_pending = False
            if self.device is not device:
                return  # connection has since been replaced
            if error is None:
                self._show_angle(counts)
                return
            if isinstance(error, DEVICE_LOST_ERRORS):
                self._stop_angle_poll()
                self.toast(f"Reading wheel angle failed: {error}")
                self._disconnect(f"Disconnected: {error}")
                return
            now = GLib.get_monotonic_time() / 1e6
            if now - self._last_angle_toast >= ANGLE_TOAST_INTERVAL_S:
                self._last_angle_toast = now
                self.toast(f"Reading wheel angle failed: {error}")

        self.worker.run(device.read_position, done)
        return GLib.SOURCE_CONTINUE

    def _steering_range(self):
        return self.values.get("steering_range", DEFAULT_STEERING_RANGE)

    def _show_angle(self, counts):
        """Update the angle row from a raw reading (None clears it)."""
        if self.angle_row is None:
            return
        if counts is None:
            self.angle_row.set_subtitle(ANGLE_IDLE)
            return
        deg = center.counts_to_deg(counts, self._steering_range())
        self.angle_row.set_subtitle(f"{deg + 0.0:.1f}°")

    def _start_polling(self):
        if not self.poll_id:
            self.poll_id = GLib.timeout_add_seconds(POLL_SECONDS, self._poll)

    def _stop_polling(self):
        if self.poll_id:
            GLib.source_remove(self.poll_id)
            self.poll_id = 0

    def _poll(self):
        self.try_connect()
        if self.device is not None:
            self.poll_id = 0
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _watch(self):
        """While connected, notice an unplugged wheelbase without waiting for a failed write."""
        if self.device is not None and self.path is not None:
            try:
                current = hidraw.find_device()
            except hidraw.DeviceError:
                current = None
            if current != self.path:
                self._disconnect("Disconnected: wheelbase unplugged")
        return GLib.SOURCE_CONTINUE

    def _close_device(self):
        fd, self.fd, self.device, self.path = self.fd, None, None, None
        if fd is not None:
            self.worker.run(lambda: os.close(fd), lambda _r, _e: None)

    def _disconnect(self, reason):
        self._close_device()
        self._set_state(False, NO_WHEEL, reason)
        self._start_polling()

    # -- writes ----------------------------------------------------------------

    def request_change(self, control: Control, value: int):
        setting = control.setting
        previous = self.values.get(setting.key, setting.default)
        device = self.device
        if device is None:
            self.toast("Not connected")
            control.set_value(previous)
            return
        if value == previous:
            return

        def done(_result, error):
            if error is None:
                self.values[setting.key] = value
                return
            if self.device is not device:
                return  # error from a connection that has since been replaced
            # revert only if the user has not already moved the control again
            if control.get_value() == value:
                control.set_value(self.values.get(setting.key, previous))
            self.toast(f"{setting.label} failed: {error}")
            if isinstance(error, DEVICE_LOST_ERRORS):
                self._disconnect(f"Disconnected: {error}")

        self.worker.run(lambda: device.set_setting(setting, value), done)

    # -- center / save to active profile ----------------------------------------------------

    def _run_device_action(self, device, fn, on_success, failure_label):
        self.busy = True
        self._update_actions()

        def done(_result, error):
            self.busy = False
            self._update_actions()
            if error is None:
                on_success(_result)
                return
            if self.device is not device:
                return  # error from a connection that has since been replaced
            self.toast(f"{failure_label} failed: {error}")
            if isinstance(error, DEVICE_LOST_ERRORS):
                self._disconnect(f"Disconnected: {error}")

        self.worker.run(fn, done)

    def request_center(self):
        device = self.device
        if device is None or not self.connected or self.busy:
            return
        confirm(
            self,
            "Set current angle as center?",
            "The wheelbase's current wheel angle becomes the new zero.",
            "Set center",
            lambda: self._submit_center(device),
        )

    def _submit_center(self, device):
        if self.device is not device or self.busy:
            self.toast("Not connected")
            return
        self._run_device_action(device, device.center, lambda _r: self.toast("Center set"), "Center")

    def request_save(self):
        """Save the current control values into the active profile (no device I/O)."""
        if not self.can_act:
            return
        # Settle pending debounced changes first so the file matches what is applied.
        for control in self.controls.values():
            if control._timer:
                control._cancel_timer()
                control._fire()
        name = self.active_name or DEFAULT_PROFILE
        try:
            profiles.save(name, self._current_values())
        except PROFILE_ERRORS as exc:
            self.toast(f"Cannot save profile {name}: {exc}")
            return
        if self.active_name != name and not self._set_active(name):
            return
        self._refresh_profiles()
        self.toast(f"Saved profile {name}")

    # -- profiles ----------------------------------------------------------------

    def _current_values(self) -> Values:
        values = {key: c.get_value() for key, c in self.controls.items()}
        if self.torque_known:
            values[MAX_TORQUE_KEY] = int(self.torque_on)
        return values

    def _apply_loaded_profile(self, device, todo, torque):
        """Worker side of a profile load: write each setting, then torque. Returns (applied, failure, torque)."""
        applied = []
        for setting, value in todo:
            try:
                device.set_setting(setting, value)
            except Exception as exc:  # noqa: BLE001
                return applied, (setting, exc), None
            applied.append((setting, value))
        if torque is not None:
            try:
                device.set_max_torque(bool(torque))
            except Exception as exc:  # noqa: BLE001
                return applied, (MAX_TORQUE_LABEL, exc), None
        return applied, None, torque

    def _finish_load(self, name, device, result, error):
        """UI side of a profile load: reflect what was applied, report the outcome."""
        if error is not None:
            self.toast(f"Load {name} failed: {error}")
            return
        applied, failure, sent_torque = result
        for setting, value in applied:
            self.values[setting.key] = value
            self.controls[setting.key].set_value(value)
        if sent_torque is not None:
            self._set_torque(sent_torque)
        if failure is None:
            self._set_active(name)
            self.toast(f"Loaded profile {name}")
            return
        setting, exc = failure
        label = setting if isinstance(setting, str) else setting.label
        self.toast(f"Load {name} failed at {label}: {exc}")
        if isinstance(exc, DEVICE_LOST_ERRORS) and self.device is device:
            self._disconnect(f"Disconnected: {exc}")

    def _on_load(self, name):
        try:
            values = profiles.load(name)
        except PROFILE_ERRORS as exc:
            self.toast(f"Cannot load {name}: {exc}")
            return
        device = self.device
        if device is None:
            self.toast("Not connected")
            return
        todo = [
            (s, int(values[s.key]))
            for s in settings.REGISTRY
            if s.key in self.controls and s.key in values
        ]

        torque = values.get(MAX_TORQUE_KEY)
        if torque is not None and torque not in (0, 1):
            self.toast(f"Cannot load {name}: {MAX_TORQUE_KEY} must be 0 or 1")
            return

        self.worker.run(
            lambda: self._apply_loaded_profile(device, todo, torque),
            lambda result, error: self._finish_load(name, device, result, error),
        )

    def _on_delete(self, name):
        def delete():
            try:
                profiles.delete(name)
            except PROFILE_ERRORS as exc:
                self.toast(f"Cannot delete {name}: {exc}")
                return
            if name == self.active_name:
                self._set_active(None)
            self._refresh_profiles()

        confirm(self, f"Delete profile “{name}”?", "This cannot be undone.", "Delete", delete,
                destructive=True)

    def _save_profile(self, name, values):
        try:
            profiles.save(name, values)
        except PROFILE_ERRORS as exc:
            self.toast(f"Cannot save {name}: {exc}")
            return False
        self._refresh_profiles()
        self.toast(f"Saved profile {name}")
        return True

    def _save_with_overwrite_check(self, name, values, after=None):
        def do_save():
            if self._save_profile(name, values) and after:
                after()

        try:
            exists = name in profiles.list_profiles()
        except PROFILE_ERRORS:
            exists = False
        if exists:
            confirm(self, f"Overwrite “{name}”?", "A profile with this name already exists.",
                    "Overwrite", do_save, destructive=True)
        else:
            do_save()

    def _on_save_as(self, row):
        name = row.get_text().strip()
        if not profiles.NAME_RE.fullmatch(name):
            self.toast("Name must be 1-64 characters: letters, digits, space, _ or -")
            return
        self._save_with_overwrite_check(name, self._current_values(), lambda: row.set_text(""))


    def _on_export(self, name):
        try:
            values = profiles.load(name)
        except PROFILE_ERRORS as exc:
            self.toast(f"Cannot export {name}: {exc}")
            return
        dialog = Gtk.FileDialog(title=f"Export {name}", initial_name=f"{name}.json")

        def done(dlg, result):
            try:
                gfile = dlg.save_finish(result)
            except GLib.Error:
                return  # dismissed
            try:
                data = profiles.dump_profile(values) + "\n"
                Path(gfile.get_path()).write_text(data, encoding="utf-8")
            except (OSError, TypeError) as exc:
                self.toast(f"Export failed: {exc}")
                return
            self.toast(f"Exported {name}")

        dialog.save(self, None, done)

    def _on_import(self, _button):
        dialog = Gtk.FileDialog(title="Import profile")
        filt = Gtk.FileFilter(name="JSON files")
        filt.add_suffix("json")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filt)
        dialog.set_filters(filters)

        def done(dlg, result):
            try:
                gfile = dlg.open_finish(result)
            except GLib.Error:
                return
            path = Path(gfile.get_path())
            try:
                values = profiles.parse_profile(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, profiles.ProfileError) as exc:
                self.toast(f"Import failed: {exc}")
                return
            name = profiles.sanitize_name(path.stem)
            self._save_with_overwrite_check(name, values)

        dialog.open(self, None, done)

    # -- shutdown ------------------------------------------------------------------

    def _on_close(self, _window):
        self._stop_polling()
        self._stop_angle_poll()
        self._close_device()
        self.worker.stop()
        return False


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self):
        win = self.props.active_window or MainWindow(self)
        win.present()


def main(argv=None) -> int:
    return App().run(sys.argv if argv is None else argv)
