import unittest

from obelisk import protocol, settings
from obelisk.errors import SettingError

# Page-3 payload from capture/02-filter.pcapng, t=27.699 (Overall Filter typed as 100).
P100 = bytes.fromhex("000000000150bc0384031027000091010000000000002823102710271027102710271027102710271027102710270310270008aa")
S = next(s for s in settings.REGISTRY if s.key == "overall_filter")


class OverallFilter(unittest.TestCase):
    def test_captured_values(self):
        # (typed value, captured wire bytes at idx 14..15): t=27.699, 37.691, 47.699, 60.695
        for value, wire in ((100, "9101"), (300, "c900"), (470, "1f00"), (276, "e100")):
            out = protocol.set_value(S, P100, value)
            self.assertEqual(out[14:16].hex(), wire)
            self.assertEqual(out[:14] + out[16:], P100[:14] + P100[16:])
            self.assertEqual(protocol.get_value(S, out), value)

    def test_zero_is_wire_zero_like_simcenter(self):
        # capture/09-ranges.pcapng: UI 0 -> wire 0, UI 500 -> wire 1
        for value, wire in ((0, 0), (500, 1)):
            out = protocol.set_value(S, P100, value)
            self.assertEqual(int.from_bytes(out[14:16], "little"), wire)
            self.assertEqual(protocol.get_value(S, out), value)

    def test_range(self):
        for bad in (S.min - 1, S.max + 1):
            with self.assertRaises(SettingError):
                protocol.set_value(S, P100, bad)


if __name__ == "__main__":
    unittest.main()
