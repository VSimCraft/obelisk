import errno
import os
import unittest
from unittest import mock

from obelisk import hidraw


class LostDevice(unittest.TestCase):
    def test_unplugged_errnos_raise_device_lost(self):
        for code in (errno.EIO, errno.ENODEV):
            with mock.patch.object(os, "write", side_effect=OSError(code, "gone")), \
                    self.assertRaises(hidraw.DeviceLost):
                hidraw.write_report(3, 0x14, b"\0" * 63)
            with mock.patch.object(hidraw.select, "select", side_effect=OSError(code, "gone")), \
                    self.assertRaises(hidraw.DeviceLost):
                hidraw.read_report(3, 0.1)

    def test_other_errors_are_plain_device_error(self):
        with mock.patch.object(os, "write", side_effect=OSError(errno.EINVAL, "bad")), \
                self.assertRaises(hidraw.DeviceError) as cm:
            hidraw.write_report(3, 0x14, b"\0" * 63)
        self.assertNotIsInstance(cm.exception, hidraw.DeviceLost)


if __name__ == "__main__":
    unittest.main()
