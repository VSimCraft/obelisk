import os
import sys


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


if "--apply" in sys.argv[1:]:
    sys.exit(apply_startup())

from .gui import main

sys.exit(main())
