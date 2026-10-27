import os
import tempfile
import unittest
from unittest import mock

from obelisk import device, hidraw, profiles, protocol, settings
from obelisk.errors import SettingError

S = {s.key: s for s in settings.REGISTRY}

# Real bytes: capture/04-center-*.pcapng (first 12 bytes after the report ID).
CENTER_HEAD = bytes.fromhex("0c070500000000000000" "00")


class Center(unittest.TestCase):
    def test_center_matches_capture(self):
        rid, p = protocol.center_request()
        self.assertEqual((rid, p[:11], len(p)), (0x14, CENTER_HEAD[:11], 63))


class Wheel:
    """Models pages in RAM like the real wheelbase (reads reply, page writes store)."""

    def __init__(self):
        self.pages = {3: bytearray(52), 5: bytearray(28), 8: bytearray(7)}
        self.pages[3][8:10] = (900).to_bytes(2, "little")
        self.pages[3][22:24] = (9000).to_bytes(2, "little")
        self.pages[3][14:16] = (225).to_bytes(2, "little")      # Overall Filter 276
        self.pages[5][2:4] = (300).to_bytes(2, "little")        # Damper 3
        self.pages[5][6:8] = (200).to_bytes(2, "little")        # Friction 2
        self.inbox, self.writes = [], []

    def write_report(self, fd, rid, p):
        if p[0] == 0x0C and p[1] == 0x0A:
            self.inbox.append((bytes([0x41, p[3], p[4]]) + bytes(self.pages[p[3]])).ljust(64, b"\0"))
        elif p[1:3] == b"\x07\x01":
            page, n = p[3], p[6]
            self.writes.append(page)
            self.pages[page][:] = p[7:7 + n]

    def read_report(self, fd, timeout):
        return self.inbox.pop(0) if self.inbox else None


class ApplyValues(unittest.TestCase):
    def setUp(self):
        self.w = Wheel()
        for n in ("write_report", "read_report"):
            p = mock.patch.object(hidraw, n, getattr(self.w, n)); p.start(); self.addCleanup(p.stop)
        self.dev = device.Device(-1)

    def test_only_differing_values_written_batched_per_page(self):
        out = self.dev.apply_values({"steering_range": 540, "overall_gain": 90, "overall_filter": 300,
                                     "damper_gain": 7, "friction_gain": 2})
        self.assertEqual(out, {"steering_range": 540, "overall_filter": 300, "damper_gain": 7})
        self.assertEqual(sorted(self.w.writes), [3, 5])          # one write per touched page
        self.assertEqual(self.dev.read_all()["steering_range"], 540)
        self.assertEqual(self.dev.read_all()["overall_gain"], 90)  # untouched

    def test_nothing_to_do_writes_nothing(self):
        self.assertEqual(self.dev.apply_values({"steering_range": 900, "overall_gain": 90}), {})
        self.assertEqual(self.w.writes, [])

    def test_out_of_range_rejected_before_any_write(self):
        with self.assertRaises(SettingError):
            self.dev.apply_values({"damper_gain": 7, "steering_range": 5000})
        self.assertEqual(self.w.writes, [])

    def test_unknown_keys_ignored(self):
        self.assertEqual(self.dev.apply_values({"nope": 1}), {})


class MaxTorque(unittest.TestCase):
    def setUp(self):
        self.w = Wheel()
        self.sent = []
        orig = self.w.write_report
        def spy(fd, rid, p):
            self.sent.append(bytes([rid]) + p); orig(fd, rid, p)
        for n, f in (("write_report", spy), ("read_report", self.w.read_report)):
            q = mock.patch.object(hidraw, n, f); q.start(); self.addCleanup(q.stop)
        self.dev = device.Device(-1)

    def test_bytes_match_capture_10(self):
        # capture/10-max-torque-mode.pcapng: 14 0d 00 ec 00 00 00 00 <m>
        self.assertEqual(protocol.max_torque_request(False)[1][:8], bytes.fromhex("0d00ec0000000000"))
        self.assertEqual(protocol.max_torque_request(True)[1][:8], bytes.fromhex("0d00ec0000000001"))

    def test_apply_sends_it_once_per_connection_and_again_when_it_changes(self):
        key = settings.MAX_TORQUE_KEY
        self.assertEqual(self.dev.apply_values({key: 1}), {key: 1})
        self.assertEqual(self.dev.apply_values({key: 1}), {})             # already sent on this connection
        self.assertEqual(self.dev.apply_values({key: 0}), {key: 0})
        modes = [r[8] for r in self.sent if r[1] == 0x0D and r[3] == 0xEC]
        self.assertEqual(modes, [1, 0])

    def test_profile_without_the_key_sends_nothing(self):
        self.dev.apply_values({"overall_gain": 90})
        self.assertFalse([r for r in self.sent if r[1] == 0x0D])

    def test_invalid_mode_rejected_before_any_write(self):
        with self.assertRaises(SettingError):
            self.dev.apply_values({settings.MAX_TORQUE_KEY: 2, "damper_gain": 7})
        self.assertEqual(self.w.writes, [])
        self.assertFalse(self.sent)


class ActiveProfile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name}); p.start(); self.addCleanup(p.stop)

    def test_none_selected_by_default(self):
        self.assertIsNone(profiles.get_active())
        self.assertIsNone(profiles.load_active())

    def test_select_load_and_clear(self):
        profiles.save("race", {"overall_gain": 55, "overall_filter": 300})
        profiles.set_active("race")
        self.assertEqual(profiles.load_active(), ("race", {"overall_gain": 55, "overall_filter": 300}))
        profiles.set_active(None)
        self.assertIsNone(profiles.load_active())

    def test_invalid_name_rejected_and_state_untouched(self):
        profiles.save("a", {"x": 1}); profiles.set_active("a")
        with self.assertRaises(profiles.ProfileError):
            profiles.set_active("../evil")
        self.assertEqual(profiles.get_active(), "a")

    def test_active_profile_missing_or_corrupt_raises(self):
        profiles.save("a", {"x": 1}); profiles.set_active("a")
        (profiles.config_dir() / "profiles" / "a.json").write_text("{broken")
        with self.assertRaises(profiles.ProfileError):
            profiles.load_active()
        (profiles.config_dir() / "profiles" / "a.json").unlink()
        with self.assertRaises(profiles.ProfileError):
            profiles.load_active()


class SteeringRange(unittest.TestCase):
    def test_limits_match_simcenter_slider(self):
        st = S["steering_range"]
        self.assertEqual((st.min, st.max), (180, 1080))
        for v in (180, 1080):
            out = protocol.set_value(st, bytes(52), v)
            self.assertEqual(protocol.get_value(st, out), v)
        for bad in (179, 1081):
            with self.assertRaises(SettingError):
                protocol.set_value(st, bytes(52), bad)


class FilterRange(unittest.TestCase):
    def test_slider_range_matches_simcenter(self):
        self.assertEqual((S["overall_filter"].min, S["overall_filter"].max), (0, 500))
        for v in (0, 500):
            out = protocol.set_value(S["overall_filter"], bytes(52), v)
            self.assertEqual(protocol.get_value(S["overall_filter"], out), v)


if __name__ == "__main__":
    unittest.main()
