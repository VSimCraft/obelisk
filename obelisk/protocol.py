"""Pure byte builders/parsers for the VNM vendor channel (no I/O).

Wire format: docs/protocol.md. All "payload63" values are the bytes that
follow the report-ID byte in a 64-byte report (what hidraw.write_report takes).
"""
from .errors import SettingError
from .settings import REGISTRY, Setting, Values

PAYLOAD_SIZE = 63
CMD_REPORT_ID = 0x14
REPLY_REPORT_ID = 0x41
PAGE_LEN = {3: 52, 5: 28, 8: 7}
PAGE_SEQ = {3: 0xE3, 5: 0xE4, 8: 0xEA}
AXIS_REPORT_ID = 0x01
AXIS_REPORT_MIN_LEN = 19


def _pad(b: bytes) -> bytes:
    return b.ljust(PAYLOAD_SIZE, b"\0")


def _check_page(page: int) -> None:
    if page not in PAGE_LEN:
        raise ValueError(f"unknown page {page}")


def read_request(page: int) -> tuple[int, bytes]:
    """14 0c 0a 00 <page> <seq> 00 00 ff ff ff ff, zero padded."""
    _check_page(page)
    return CMD_REPORT_ID, _pad(bytes([0x0C, 0x0A, 0x00, page, PAGE_SEQ[page], 0, 0, 0xFF, 0xFF, 0xFF, 0xFF]))


def write_request(page: int, payload: bytes) -> tuple[int, bytes]:
    """14 <len+12> 07 01 <page> 00 00 <len> <payload>, zero padded."""
    _check_page(page)
    n = PAGE_LEN[page]
    if len(payload) != n:
        raise ValueError(f"page {page} payload must be {n} bytes, got {len(payload)}")
    return CMD_REPORT_ID, _pad(bytes([n + 12, 0x07, 0x01, page, 0, 0, n]) + bytes(payload))


def parse_reply(report: bytes) -> tuple[int, int, bytes] | None:
    """41 <page> <seq> <payload...> -> (page, seq, payload); None for anything else."""
    if len(report) < 3 or report[0] != REPLY_REPORT_ID:
        return None
    page = report[1]
    n = PAGE_LEN.get(page)
    if n is None or len(report) < 3 + n:
        return None
    return page, report[2], bytes(report[3:3 + n])


def firmware_request() -> tuple[int, bytes]:
    """Firmware version request: 14 0c 0b 00 00 e0, zero padded. The wheel then streams the reply until the next request."""
    return CMD_REPORT_ID, _pad(bytes([0x0C, 0x0B, 0x00, 0x00, 0xE0]))


def parse_firmware(report: bytes) -> str | None:
    """41 00 <seq> a b c d -> "a.b.c.d"; None for anything else."""
    if len(report) < 7 or report[0] != REPLY_REPORT_ID or report[1] != 0:
        return None
    return ".".join(str(b) for b in report[3:7])


def parse_axis(report: bytes) -> int | None:
    """Axis report 0x01: signed le16 at bytes 17..18 (counts); None if the report is not one."""
    if len(report) < AXIS_REPORT_MIN_LEN or report[0] != AXIS_REPORT_ID:
        return None
    return int.from_bytes(report[17:19], "little", signed=True)


def center_request() -> tuple[int, bytes]:
    """Set the current wheel position as the new zero: 14 0c 07 05 00 x8.

    Identical in capture/04-center-30-deg-left.pcapng (t=6.319) and
    04b-center-90-deg-right.pcapng (t=5.813); the wheelbase sends no reply.
    SimCenter's trailing bytes are uninitialised memory (same in both files); zeroed here.
    """
    return CMD_REPORT_ID, _pad(bytes([0x0C, 0x07, 0x05]) + bytes(8))


def max_torque_request(on: bool) -> tuple[int, bytes]:
    """Max Torque Mode: 14 0d 00 ec 00 00 00 00 <m>, m = 1 ON / 0 OFF; no reply.

    capture/10-max-torque-mode.pcapng: t=27.68 m=0 (toggle OFF), t=76.18 m=1 (toggle ON); also sent
    with m=1 once at SimCenter launch (capture 07, t=16.10). Independent of Apply (pages 3/5/8).
    """
    return CMD_REPORT_ID, _pad(bytes([0x0D, 0x00, 0xEC, 0, 0, 0, 0, 1 if on else 0]))


def _check_span(setting: Setting, page_payload: bytes) -> None:
    if setting.offset < 0 or setting.offset + setting.width > len(page_payload):
        raise ValueError(f"{setting.key}: offset/width outside page payload")


def get_value(setting: Setting, page_payload: bytes) -> int:
    _check_span(setting, page_payload)
    raw = int.from_bytes(page_payload[setting.offset:setting.offset + setting.width], "little")
    if setting.invert is not None and raw != 0:   # wire 0 is UI 0 (capture/09-ranges.pcapng), not invert
        raw = setting.invert - raw
    return round(raw * setting.scale)


def set_value(setting: Setting, page_payload: bytes, value: int) -> bytes:
    if not setting.min <= value <= setting.max:
        raise SettingError(f"{setting.key}: {value} outside [{setting.min}, {setting.max}]")
    _check_span(setting, page_payload)
    raw = round(value / setting.scale)
    if setting.invert is not None and raw != 0:   # UI 0 is written as wire 0, not `invert`
        raw = setting.invert - raw
    try:
        field = raw.to_bytes(setting.width, "little")
    except OverflowError as e:
        raise SettingError(f"{setting.key}: raw {raw} does not fit {setting.width} bytes") from e
    buf = bytearray(page_payload)
    buf[setting.offset:setting.offset + setting.width] = field
    return bytes(buf)


def decode(report: bytes) -> Values:
    parsed = parse_reply(report)
    if parsed is None:
        return {}
    page, _, payload = parsed
    return {s.key: get_value(s, payload) for s in REGISTRY if s.page == page}
