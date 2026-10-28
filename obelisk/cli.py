"""Command line entry point (`obelisk`, `python -m obelisk`)."""
import argparse
import os
import sys
from importlib import resources
from pathlib import Path

from . import __version__

UDEV_RULE = "70-vnm-direct-drive.rules"
DESKTOP_FILE = "io.github.vsimcraft.obelisk.desktop"
GI_HINT = (
    "obelisk: GTK4 and libadwaita bindings not found. Install your distribution's PyGObject, GTK4 and "
    "libadwaita packages, and install Obelisk with `pipx install --system-site-packages obelisk-ffb` "
    "using the system Python (see the README)."
)


def apply_startup() -> int:
    """Headless: apply the active profile to the wheelbase and exit (no GUI, no GTK import)."""
    from . import hidraw, profiles
    from .device import Device
    from .errors import VnmError

    try:
        active = profiles.load_active()
        if active is None:
            print("no active profile selected")
            return 0
        name, values = active
        fd = hidraw.open_device(hidraw.find_device())
    except VnmError as exc:
        print(f"obelisk: {exc}", file=sys.stderr)
        return 1
    try:
        written = Device(fd).apply_values(values)
    except VnmError as exc:
        print(f"obelisk: applying profile failed: {exc}", file=sys.stderr)
        return 1
    finally:
        os.close(fd)
    print(f"profile {name}: applied {len(written)} changed value(s): {written}" if written
          else f"profile {name}: already up to date")
    return 0


def data_text(name: str) -> str:
    return resources.files("obelisk").joinpath("data", name).read_text(encoding="utf-8")


def _exec_arg(arg: str) -> str:
    """Quote one Exec= argument per the Desktop Entry spec."""
    if not any(c in arg for c in ' \t\n"\'\\><~|&;$*?#()`%'):
        return arg
    escaped = "".join("\\" + c if c in '"`$\\' else c for c in arg)
    return f'"{escaped}"'.replace("%", "%%")


def desktop_entry(command: list[str]) -> str:
    return data_text(DESKTOP_FILE).replace("@EXEC@", " ".join(_exec_arg(a) for a in command))


def install_desktop(command: list[str]) -> int:
    """Write the user-level app-menu entry launching `command`."""
    base = os.environ.get("XDG_DATA_HOME")
    apps = (Path(base) if base else Path.home() / ".local" / "share") / "applications"
    apps.mkdir(parents=True, exist_ok=True)
    target = apps / DESKTOP_FILE
    target.write_text(desktop_entry(command), encoding="utf-8")
    target.chmod(0o644)
    print(f"installed {target}")
    return 0


def _command() -> list[str]:
    """Absolute `obelisk` command for the menu entry, falling back to `python -m obelisk`."""
    argv0 = Path(sys.argv[0])
    if argv0.name == "obelisk" and argv0.is_file():
        return [str(argv0.absolute())]
    return [sys.executable, "-m", "obelisk"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="obelisk", description="Settings tool for the VNM Xtreme 32 Nm wheelbase.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="apply the active profile without opening a window")
    group.add_argument("--print-udev-rule", action="store_true",
                       help="print the udev rule that grants hidraw access (pipe it to sudo tee)")
    group.add_argument("--install-desktop", action="store_true", help="install the app-menu entry for this user")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.apply:
        return apply_startup()
    if args.print_udev_rule:
        sys.stdout.write(data_text(UDEV_RULE))
        return 0
    if args.install_desktop:
        return install_desktop(_command())
    try:
        from .gui import main as gui_main
    except ModuleNotFoundError as exc:
        if exc.name != "gi":
            raise
        print(GI_HINT, file=sys.stderr)
        return 1
    except ValueError:  # gi.require_version: namespace not installed
        print(GI_HINT, file=sys.stderr)
        return 1
    return gui_main([sys.argv[0]])
