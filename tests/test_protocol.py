import unittest
from unittest import mock

from obelisk import device, hidraw, protocol
from obelisk.errors import SettingError
from obelisk.settings import REGISTRY

S = {s.key: s for s in REGISTRY}

# Bytes copied from capture/vnm.pcapng (usbmon_parse.py --dev 18 --ids 14,41).
# Page 3 writes: wire bytes after the report-ID, 8-byte header + 52 payload.
P3_551 = bytes.fromhex("000000000150bc03840310270000e1000000000000002823102710271027102710271027102710271027102710270310270008aa")
P3_1160 = bytes.fromhex("000000000150bc03a40210270000e1000000000000002823102710271027102710271027102710271027102710270310270008aa")
P3_903_37 = bytes.fromhex("000000000150bc03870310270000e100000000000000740e102710271027102710271027102710271027102710270310270008aa")
HDR3 = bytes.fromhex("1440070103000034")
HDR5 = bytes.fromhex("142807010500001c")
P5_551 = bytes.fromhex("10272c011027c8001027000010270000000010271027102700000000")
P5_DAMPER = bytes.fromhex("102708201027c8001027000010270000000010271027102700000000")  # t=79.606
P5_FRICTION = bytes.fromhex("10272c011027d4171027000010270000000010271027102700000000")  # t=90.607
P5_INERTIA = bytes.fromhex("10272c011027c8001027602210270000000010271027102700000000")  # t=100.606
P5_SPRING = bytes.fromhex("10272c011027c800102700001027a41f000010271027102700000000")  # t=110.605
HEARTBEAT = bytes.fromhex("41aa91000100000000b89fe241d53125422818d841030000000a0000000000426666e6410000e14500006144f883ce408ab5373d27320dc10068010068010000")


class Fixtures(unittest.TestCase):
    def test_fixture_lengths(self):
        for p in (P3_551, P3_1160, P3_903_37):
            self.assertEqual(len(p), 52)
        for p in (P5_551, P5_DAMPER, P5_FRICTION, P5_INERTIA, P5_SPRING):
            self.assertEqual(len(p), 28)


class WriteRequest(unittest.TestCase):
    def test_page3_first_and_changed(self):
        for payload, expected in ((P3_551, P3_551), (P3_1160, P3_1160)):
            rid, data = protocol.write_request(3, payload)
            self.assertEqual(rid, 0x14)
            self.assertEqual(len(data), 63)
            self.assertEqual(bytes([rid]) + data[:7 + 52], HDR3 + expected)
            self.assertEqual(data[7 + 52:], b"\0" * 4)

    def test_page5_header(self):
        rid, data = protocol.write_request(5, P5_551)
        self.assertEqual(bytes([rid]) + data[:7 + 28], HDR5 + P5_551)
        self.assertEqual(len(data), 63)

    def test_bad_length_and_page(self):
        with self.assertRaises(ValueError):
            protocol.write_request(3, b"\0" * 51)
        with self.assertRaises(ValueError):
            protocol.write_request(4, b"\0" * 52)

    def test_read_request(self):
        rid, data = protocol.read_request(3)
        self.assertEqual(rid, 0x14)
        self.assertEqual(len(data), 63)
        self.assertEqual(bytes([rid]) + data[:11], bytes.fromhex("140c0a0003e30000ffffffff"))
        self.assertEqual(data[11:], b"\0" * 52)
        self.assertEqual(protocol.read_request(5)[1][4], 0xE4)
        self.assertEqual(protocol.read_request(8)[1][4], 0xEA)


class Values(unittest.TestCase):
    def test_get(self):
        self.assertEqual(protocol.get_value(S["steering_range"], P3_551), 900)
        self.assertEqual(protocol.get_value(S["overall_gain"], P3_551), 90)
        self.assertEqual(protocol.get_value(S["damper_gain"], P5_551), 3)
        self.assertEqual(protocol.get_value(S["friction_gain"], P5_551), 2)

    def test_steering(self):
        self.assertEqual(protocol.set_value(S["steering_range"], P3_551, 676), P3_1160)

    def test_overall_gain(self):
        # t=38.605 write: steering was already 903 at that point in the capture
        base = protocol.set_value(S["steering_range"], P3_551, 903)
        out = protocol.set_value(S["overall_gain"], base, 37)
        self.assertEqual(out, P3_903_37)
        self.assertEqual(out[22:24], bytes.fromhex("740e"))

    def test_page5_fields(self):
        self.assertEqual(protocol.set_value(S["damper_gain"], P5_551, 82), P5_DAMPER)
        self.assertEqual(protocol.set_value(S["friction_gain"], P5_551, 61), P5_FRICTION)
        self.assertEqual(protocol.set_value(S["inertia_gain"], P5_551, 88)[10:12], (8800).to_bytes(2, "little"))
        self.assertEqual(protocol.set_value(S["spring_gain"], P5_551, 81)[14:16], (8100).to_bytes(2, "little"))

    def test_unrelated_bytes_untouched(self):
        for s in REGISTRY:
            page = P3_551 if s.page == 3 else P5_551
            out = protocol.set_value(s, page, s.max)
            self.assertEqual(len(out), len(page))
            self.assertEqual(out[:s.offset], page[:s.offset])
            self.assertEqual(out[s.offset + s.width:], page[s.offset + s.width:])

    def test_range_rejected(self):
        for s in REGISTRY:
            page = P3_551 if s.page == 3 else P5_551
            for v in (s.min - 1, s.max + 1):
                with self.assertRaises(SettingError):
                    protocol.set_value(s, page, v)
            protocol.set_value(s, page, s.min)
            protocol.set_value(s, page, s.max)


class Replies(unittest.TestCase):
    def test_parse_page3(self):
        report = bytes.fromhex("4103e3") + P3_551 + b"\0" * 9
        self.assertEqual(len(report), 64)
        self.assertEqual(protocol.parse_reply(report), (3, 0xE3, P3_551))

    def test_heartbeat_and_others(self):
        self.assertEqual(len(HEARTBEAT), 64)
        self.assertIsNone(protocol.parse_reply(HEARTBEAT))
        self.assertIsNone(protocol.parse_reply(b"\x14" + bytes(63)))
        self.assertIsNone(protocol.parse_reply(bytes.fromhex("4107fd9000") + bytes(59)))

    def test_firmware(self):
        self.assertEqual(protocol.parse_firmware(bytes.fromhex("41000001010133") + bytes(57)), "1.1.1.51")
        self.assertIsNone(protocol.parse_firmware(HEARTBEAT))
        self.assertIsNone(protocol.parse_firmware(bytes.fromhex("4103e3") + bytes(61)))

    def test_decode(self):
        report = bytes.fromhex("4103e3") + P3_551 + b"\0" * 9
        self.assertEqual(protocol.decode(report),
                         {"steering_range": 900, "overall_gain": 90, "overall_filter": 276})
        self.assertEqual(protocol.decode(HEARTBEAT), {})


def axis_report(value: int) -> bytes:
    return bytes([0x01]) + bytes(16) + value.to_bytes(2, "little", signed=True) + bytes(45)


class AxisReport(unittest.TestCase):
    def test_signed_value(self):
        self.assertEqual(protocol.parse_axis(axis_report(6606)), 6606)
        self.assertEqual(protocol.parse_axis(axis_report(-2307)), -2307)

    def test_wrong_id_or_short_is_none(self):
        self.assertIsNone(protocol.parse_axis(bytes([0x14]) + axis_report(6606)[1:]))
        self.assertIsNone(protocol.parse_axis(axis_report(6606)[:18]))



class FakeWheel:
    """Stands in for hidraw.write_report/read_report; models pages in RAM."""

    def __init__(self):
        self.pages = {3: bytearray(P3_551), 5: bytearray(P5_551), 8: bytearray(7)}
        self.writes = []  # (report_id, payload63)
        self.inbox = [HEARTBEAT, bytes.fromhex("4105e4") + bytes(61)]  # stale input

    def write_report(self, fd, report_id, payload63):
        assert len(payload63) == 63
        self.writes.append((report_id, bytes(payload63)))
        if payload63[0] == 0x0C:  # read request
            page = payload63[3]
            self.inbox.append(HEARTBEAT)
            self.inbox.append((bytes([0x41, page, payload63[4]]) + bytes(self.pages[page])).ljust(64, b"\0"))
        elif payload63[1:3] == b"\x07\x01":
            pass

    def read_report(self, fd, timeout):
        return self.inbox.pop(0) if self.inbox else None


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.wheel = FakeWheel()
        for name in ("write_report", "read_report"):
            p = mock.patch.object(hidraw, name, getattr(self.wheel, name))
            p.start()
            self.addCleanup(p.stop)
        self.dev = device.Device(-1)

    def test_set_setting_single_write_preserves_bytes(self):
        self.wheel.pages[3][8:10] = (903).to_bytes(2, "little")
        v = self.dev.set_setting(S["overall_gain"], 37)
        self.assertEqual(v, 37)
        page_writes = [w for w in self.wheel.writes if w[1][1:3] == b"\x07\x01"]
        self.assertEqual(len(page_writes), 1)
        rid, data = page_writes[0]
        self.assertEqual(rid, 0x14)
        self.assertEqual(bytes([rid]) + data[:7 + 52], HDR3 + P3_903_37)
        # exactly one read request + one write: nothing else was sent
        self.assertEqual(len(self.wheel.writes), 2)

    def test_set_setting_page5(self):
        self.dev.set_setting(S["friction_gain"], 61)
        _rid, data = self.wheel.writes[-1]
        self.assertEqual(data[7:7 + 28], P5_FRICTION)

    def test_stale_replies_ignored(self):
        self.assertEqual(self.dev.read_page(5), P5_551)

    def test_drain_survives_endless_input(self):
        axis = bytes([0x01]) + bytes(63)
        self.wheel.read_report = lambda fd, timeout: axis  # never empty
        with mock.patch.object(hidraw, "read_report", self.wheel.read_report):
            self.dev._drain()  # must return

    def test_read_all(self):
        self.assertEqual(self.dev.read_all(), {
            "steering_range": 900, "overall_gain": 90, "overall_filter": 276, "damper_gain": 3,
            "friction_gain": 2, "inertia_gain": 0, "spring_gain": 0})

    def test_out_of_range_sends_nothing_after_read(self):
        with self.assertRaises(SettingError):
            self.dev.set_setting(S["steering_range"], 5000)
        self.assertFalse([w for w in self.wheel.writes if w[1][1:3] == b"\x07\x01"])

    def test_timeout(self):
        with mock.patch.object(hidraw, "read_report", lambda fd, t: None), self.assertRaises(hidraw.DeviceError):
            self.dev.read_page(3, timeout=0.05)


if __name__ == "__main__":
    unittest.main()
