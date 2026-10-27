"""Headless-safe GTK smoke test: builds the real window with no device attached.

Skipped when GTK4/libadwaita or a display is unavailable. Never touches hardware: device discovery is patched out.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from gi.repository import Adw, Gio, GLib, Gtk

    from obelisk import gui, hidraw, profiles, settings
    Adw.init()
    HAVE_GTK = bool(Gtk.init_check())
except (ImportError, ValueError):
    HAVE_GTK = False


def spin(predicate, timeout=2.0):
    ctx = GLib.MainContext.default()
    end = GLib.get_monotonic_time() + int(timeout * 1e6)
    while not predicate() and GLib.get_monotonic_time() < end:
        ctx.iteration(False)
    return predicate()


@unittest.skipUnless(HAVE_GTK, "GTK4/libadwaita or display unavailable")
class WindowSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Adw.Application(application_id="io.github.obelisk.test", flags=Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = Path(tmp.name)
        for p in (
            mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(home / "cfg"), "HOME": str(home)}),
            mock.patch.object(hidraw, "find_device", side_effect=hidraw.DeviceError("not found")),
        ):
            p.start()
            self.addCleanup(p.stop)
        profiles.save("alpha", {"overall_gain": 50})
        self.win = gui.MainWindow(self.app)
        self.addCleanup(self.win.worker.stop)

    def test_builds_one_control_per_int_setting_without_device(self):
        keys = {s.key for s in settings.REGISTRY if s.kind == "int"}
        self.assertEqual(set(self.win.controls), keys)
        self.assertIsNone(self.win.device)
        self.assertFalse(self.win.connected)

    def test_worker_result_is_delivered_on_main_loop(self):
        got = []
        self.win.worker.run(lambda: 41 + 1, lambda result, error: got.append((result, error)))
        self.assertTrue(spin(lambda: got))
        self.assertEqual(got, [(42, None)])

    def test_worker_exception_is_delivered_not_raised(self):
        got = []

        def boom():
            raise OSError("x")

        self.win.worker.run(boom, lambda result, error: got.append((result, error)))
        self.assertTrue(spin(lambda: got))
        self.assertIsNone(got[0][0])
        self.assertIsInstance(got[0][1], OSError)

    def test_profile_list_shows_saved_profile_and_load_requires_device(self):
        self.win._refresh_profiles()
        titles = [r.get_title() for r in self.win._profile_rows]
        self.assertEqual(titles, ["alpha"])
        with mock.patch.object(self.win, "toast") as toast:
            self.win._on_load("alpha")
        toast.assert_called_once_with("Not connected")

    def test_can_act_requires_connection_and_idle(self):
        self.assertFalse(self.win.can_act)
        self.win.connected = True
        self.assertTrue(self.win.can_act)
        self.win.busy = True
        self.assertFalse(self.win.can_act)


if __name__ == "__main__":
    unittest.main()
