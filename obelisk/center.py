"""Converts raw axis position counts to a steering angle in degrees (relative to the last Center).

Axis report 0x01: signed le16 at bytes 17..18, +/-32767 = +/-(steering_range / 2) degrees
(capture/04-center-*.pcapng: -2307 counts at ~30 deg left, 6606 at ~90 deg right, range 900).
"""

COUNTS_FULL_SCALE = 32767


def counts_to_deg(counts: int, steering_range: float) -> float:
    return counts * (steering_range / 2) / COUNTS_FULL_SCALE
