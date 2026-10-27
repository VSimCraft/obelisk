import unittest

from obelisk import hidraw, wheels


class WheelDatabase(unittest.TestCase):
    def test_supported_device_is_in_database(self):
        wheel = wheels.lookup(hidraw.USB_ID)
        self.assertEqual((wheel.name, wheel.max_torque_nm), ("VNM Xtreme 32Nm", 32))

    def test_lookup_is_case_insensitive_and_unknown_is_none(self):
        self.assertIsNotNone(wheels.lookup("0483:A3D5"))
        self.assertIsNone(wheels.lookup("dead:beef"))


if __name__ == "__main__":
    unittest.main()
