"""Page-level access to the wheelbase over an already-open hidraw fd."""
import threading
import time

from . import hidraw, protocol
from .errors import SettingError
from .hidraw import DeviceError
from .settings import MAX_TORQUE_KEY, REGISTRY, Setting, Values


class Device:
    def __init__(self, fd: int):
        self.fd = fd
        self._lock = threading.Lock()
        self.max_torque: bool | None = None  # last mode we sent on this connection (the wheel can't report it)

    def _drain(self) -> None:
        # The wheel streams ~1 kHz axis reports (ID 0x01), so "until empty" never
        # ends: drop whatever is already queued, but give up after 20 ms.
        deadline = time.monotonic() + 0.02
        while time.monotonic() < deadline and hidraw.read_report(self.fd, 0) is not None:
            pass

    def read_page(self, page: int, timeout: float = 1.0) -> bytes:
        """Caller must hold self._lock (plain Lock, not reentrant)."""
        rid, payload = protocol.read_request(page)
        self._drain()
        hidraw.write_report(self.fd, rid, payload)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DeviceError(f"timeout reading page {page}")
            report = hidraw.read_report(self.fd, remaining)
            if report is None:
                continue
            parsed = protocol.parse_reply(report)
            if parsed is not None and parsed[0] == page:
                return parsed[2]

    def write_page(self, page: int, payload: bytes) -> None:
        """Caller must hold self._lock (plain Lock, not reentrant)."""
        rid, data = protocol.write_request(page, payload)
        hidraw.write_report(self.fd, rid, data)

    def set_setting(self, setting: Setting, value: int) -> int:
        """Read-modify-write one setting's page; returns the stored value."""
        with self._lock:
            page = self.read_page(setting.page)
            new = protocol.set_value(setting, page, value)
            self.write_page(setting.page, new)
            return protocol.get_value(setting, new)

    def read_all(self) -> Values:
        out: Values = {}
        with self._lock:
            for page in dict.fromkeys(s.page for s in REGISTRY):
                payload = self.read_page(page)
                for s in REGISTRY:
                    if s.page == page:
                        out[s.key] = protocol.get_value(s, payload)
        return out

    def read_firmware(self, timeout: float = 1.0) -> str:
        """Firmware version such as "1.1.1.51". Caller must hold self._lock."""
        rid, payload = protocol.firmware_request()
        self._drain()
        hidraw.write_report(self.fd, rid, payload)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DeviceError("timeout reading firmware version")
            report = hidraw.read_report(self.fd, remaining)
            version = None if report is None else protocol.parse_firmware(report)
            if version is not None:
                return version

    def read_position(self, timeout: float = 0.5) -> int:
        """Newest steering position in counts (signed le16 at axis-report bytes 17..18), relative to the last Center.

        The wheel streams ~1000 axis reports/s and the kernel queues up to 64 per reader. Reading one
        report per poll would return the oldest queued one (seconds stale at 5 Hz), so everything already
        queued is consumed and only the newest axis report is used.
        """
        end = time.monotonic() + timeout
        latest = None
        reads = 0
        with self._lock:
            while True:
                remaining = end - time.monotonic()
                if remaining <= 0 and latest is None:
                    raise DeviceError("timeout reading steering position")
                # block only while nothing usable has been seen; afterwards just empty the queue
                r = hidraw.read_report(self.fd, remaining if latest is None else 0)
                if r is None:
                    if latest is not None:
                        return latest
                    continue
                v = protocol.parse_axis(r)
                if v is not None:
                    latest = v
                reads += 1
                if reads >= 2048 and latest is not None:   # stream outpacing us: stop, we have a fresh one
                    return latest

    def set_max_torque(self, on: bool) -> None:
        """Send Max Torque Mode (no reply; the wheelbase cannot report it back)."""
        rid, data = protocol.max_torque_request(on)
        with self._lock:
            hidraw.write_report(self.fd, rid, data)
            self.max_torque = bool(on)

    def center(self) -> None:
        """Make the wheel's current position the new zero (no reply from the device)."""
        rid, data = protocol.center_request()
        with self._lock:
            hidraw.write_report(self.fd, rid, data)

    def apply_values(self, values: Values) -> Values:
        """Write every registry setting in `values` that differs from the device.

        Batched per page (one read, one write). Returns {key: value} actually written.
        Max Torque Mode (settings.MAX_TORQUE_KEY) is sent once per connection, or when it changes.
        Unknown keys are ignored; out-of-range values raise SettingError before anything is written.
        """
        torque = values.get(MAX_TORQUE_KEY)
        if torque is not None and torque not in (0, 1):
            raise SettingError(f"{MAX_TORQUE_KEY}: {torque} is not 0 or 1")
        wanted = [s for s in REGISTRY if s.key in values]
        for s in wanted:
            if not s.min <= values[s.key] <= s.max:
                raise SettingError(f"{s.key}: {values[s.key]} outside [{s.min}, {s.max}]")
        written: Values = {}
        with self._lock:
            for page in dict.fromkeys(s.page for s in wanted):
                old = payload = self.read_page(page)
                for s in wanted:
                    if s.page == page:
                        payload = protocol.set_value(s, payload, values[s.key])
                if payload != old:
                    self.write_page(page, payload)
                    for s in wanted:
                        if s.page == page and protocol.get_value(s, old) != protocol.get_value(s, payload):
                            written[s.key] = protocol.get_value(s, payload)
        # write-only state: send once per connection, and again whenever the wanted mode changes
        if torque is not None and self.max_torque != bool(torque):
            self.set_max_torque(bool(torque))
            written[MAX_TORQUE_KEY] = int(bool(torque))
        return written
