"""Device discovery and raw hidraw I/O for the VNM wheelbase vendor channel."""
import errno
import glob
import os
import select

from .errors import VnmError

USB_ID = "0483:a3d5"
HID_ID = "HID_ID=0003:%08X:%08X" % tuple(int(p, 16) for p in USB_ID.split(":"))
REPORT_SIZE = 64
HINT = "run packaging/install-udev.sh"


class DeviceError(VnmError):
    pass


class DeviceLost(DeviceError):
    """The wheelbase was unplugged or its handle went stale; reconnect to continue."""


_GONE = {errno.ENODEV, errno.EIO, errno.ENXIO, errno.EBADF, errno.ENOENT, errno.EPIPE}


def _io_error(what: str, e: OSError) -> DeviceError:
    cls = DeviceLost if e.errno in _GONE else DeviceError
    return cls(f"{what} failed: {e}")


def find_device() -> str:
    for uevent in sorted(glob.glob("/sys/class/hidraw/hidraw*/device/uevent")):
        try:
            with open(uevent) as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        if any(l.strip().upper() == HID_ID for l in lines):
            return "/dev/" + uevent.split("/")[4]
    raise DeviceError(f"VNM wheelbase ({USB_ID}) not found")


def open_device(path: str) -> int:
    try:
        return os.open(path, os.O_RDWR)
    except PermissionError as e:
        raise DeviceError(f"Permission denied opening {path} - {HINT}") from e
    except FileNotFoundError as e:
        raise DeviceError(f"{path} not found - {HINT}") from e
    except OSError as e:
        raise DeviceError(f"Cannot open {path}: {e}") from e


def write_report(fd: int, report_id: int, payload63: bytes) -> None:
    if len(payload63) > REPORT_SIZE - 1:
        raise ValueError("payload longer than 63 bytes")
    data = (bytes([report_id]) + bytes(payload63)).ljust(REPORT_SIZE, b"\0")
    try:
        n = os.write(fd, data)
    except OSError as e:
        raise _io_error("Write", e) from e
    if n != len(data):
        raise DeviceError(f"Short write ({n}/{len(data)})")


def read_report(fd: int, timeout: float) -> bytes | None:
    try:
        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            return None
        return os.read(fd, REPORT_SIZE)
    except OSError as e:
        raise _io_error("Read", e) from e
