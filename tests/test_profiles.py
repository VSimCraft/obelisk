import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from obelisk import profiles
from obelisk.profiles import ProfileError


class ProfileTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        p = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.home / "cfg"), "HOME": str(self.home)})
        p.start()
        self.addCleanup(p.stop)

    def test_roundtrip(self):
        profiles.save("my-prof_1 x", {"a": 1, "b": -2})
        self.assertTrue((self.home / "cfg/obelisk/profiles/my-prof_1 x.json").exists())
        self.assertEqual(profiles.list_profiles(), ["my-prof_1 x"])
        self.assertEqual(profiles.load("my-prof_1 x"), {"a": 1, "b": -2})
        profiles.delete("my-prof_1 x")
        self.assertEqual(profiles.list_profiles(), [])

    def test_home_fallback(self):
        del os.environ["XDG_CONFIG_HOME"]
        profiles.save("p", {"a": 1})
        self.assertTrue((self.home / ".config/obelisk/profiles/p.json").exists())

    def test_bad_names(self):
        for n in ["", "a/b", "../x", "x" * 65, "a.b"]:
            for f in (profiles.save, profiles.load, profiles.delete):
                args = (n, {}) if f is profiles.save else (n,)
                with self.subTest(name=n, fn=f.__name__), self.assertRaises(ProfileError):
                    f(*args)

    def test_corrupt_untouched(self):
        profiles.save("p", {"a": 1})
        f = self.home / "cfg/obelisk/profiles/p.json"
        f.write_text("{not json")
        with self.assertRaises(ProfileError):
            profiles.load("p")
        self.assertEqual(f.read_text(), "{not json")

    def test_parse_rejects_wrong_version(self):
        with self.assertRaises(ProfileError):
            profiles.parse_profile({"version": 2, "values": {"a": 1}})

    def test_parse_rejects_bool_values(self):
        with self.assertRaises(ProfileError):
            profiles.parse_profile({"version": 1, "values": {"a": True}})

    def test_parse_rejects_float(self):
        with self.assertRaises(ProfileError):
            profiles.parse_profile({"version": 1, "values": {"a": 1.5}})

    def test_dump_parse_roundtrip(self):
        values = {"a": 1, "b": -2}
        self.assertEqual(profiles.parse_profile(json.loads(profiles.dump_profile(values))), values)

    def test_sanitize_name(self):
        self.assertEqual(profiles.sanitize_name("my profile.v2!"), "my profile_v2_")
        self.assertEqual(profiles.sanitize_name("x" * 100), "x" * 64)
        self.assertEqual(profiles.sanitize_name(""), "imported")


if __name__ == "__main__":
    unittest.main()
