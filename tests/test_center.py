import struct
import unittest
from unittest import mock

from obelisk import center, device, hidraw


# capture/04-center-*.pcapng: -2307 counts at ~30 deg left, 6606 at ~90 deg right (range 900).
class Scale(unittest.TestCase):
    def test_counts_to_degrees_matches_captures(self):
        self.assertAlmostEqual(center.counts_to_deg(-2307, 900), -31.7, delta=0.5)   # SimCenter heartbeat said -31.6
        self.assertAlmostEqual(center.counts_to_deg(6606, 900), 90.7, delta=0.5)     # heartbeat said +90.7
        self.assertEqual(center.counts_to_deg(32767, 360), 180)


class ReadPosition(unittest.TestCase):
    def test_reads_signed_position_skipping_other_reports(self):
        axis = bytes([1]) + bytes(16) + struct.pack("<h", -2307) + bytes(18)
        queue = [bytes.fromhex("41aa91") + bytes(61), axis]
        with mock.patch.object(hidraw, "read_report", lambda fd, t: queue.pop(0) if queue else None):
            self.assertEqual(device.Device(-1).read_position(), -2307)

    def test_uses_the_newest_queued_report_not_the_oldest(self):
        # 100 reports are already queued (the kernel keeps up to 64); the answer must be the last one.
        def axis(v):
            return bytes([1]) + bytes(16) + struct.pack("<h", v) + bytes(18)
        queue = [axis(v) for v in range(100)]
        with mock.patch.object(hidraw, "read_report", lambda fd, t: queue.pop(0) if queue else None):
            self.assertEqual(device.Device(-1).read_position(), 99)
            self.assertEqual(queue, [])

    def test_endless_stream_still_returns(self):
        n = [0]
        def endless(fd, t):
            n[0] += 1
            return bytes([1]) + bytes(16) + struct.pack("<h", n[0] % 30000) + bytes(18)
        with mock.patch.object(hidraw, "read_report", endless):
            device.Device(-1).read_position()

    def test_timeout_raises(self):
        with mock.patch.object(hidraw, "read_report", lambda fd, t: None), self.assertRaises(hidraw.DeviceError):
            device.Device(-1).read_position(timeout=0.05)


if __name__ == "__main__":
    unittest.main()
