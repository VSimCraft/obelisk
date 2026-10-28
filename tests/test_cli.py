import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from obelisk import __version__, cli

DATA = Path(cli.__file__).parent / "data"


class PrintUdevRule(unittest.TestCase):
    def test_prints_shipped_rule_verbatim(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli.main(["--print-udev-rule"]), 0)
        self.assertEqual(out.getvalue(), (DATA / cli.UDEV_RULE).read_text())
        self.assertIn('ATTRS{idVendor}=="0483"', out.getvalue())


class InstallDesktop(unittest.TestCase):
    def install(self, command):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": tmp.name}), redirect_stdout(io.StringIO()):
            self.assertEqual(cli.install_desktop(command), 0)
        return (Path(tmp.name) / "applications" / cli.DESKTOP_FILE).read_text()

    def test_exec_is_the_given_command_with_no_placeholder_left(self):
        text = self.install(["/home/u/.local/bin/obelisk"])
        self.assertIn("\nExec=/home/u/.local/bin/obelisk\n", text)
        self.assertNotIn("@", text)

    def test_paths_with_spaces_are_quoted_for_exec(self):
        text = self.install(["/home/my user/bin/obelisk"])
        self.assertIn('\nExec="/home/my user/bin/obelisk"\n', text)


class Version(unittest.TestCase):
    def test_version_flag_prints_package_version(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as cm:
            cli.main(["--version"])
        self.assertEqual((cm.exception.code, out.getvalue().strip()), (0, f"obelisk {__version__}"))

    def test_apply_and_print_rule_are_mutually_exclusive(self):
        with mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit) as cm:
            cli.main(["--apply", "--print-udev-rule"])
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
