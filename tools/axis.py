#!/usr/bin/env python3
"""Print the wheelbase's live steering position (read-only; sends nothing).

Axis report 0x01: signed le16 at bytes 17..18 spans +/-(steering_range/2) degrees
(capture/04-center-*.pcapng: -2307 at ~30 deg left, 6606 at ~90 deg right, 0 right after Center).
usage: tools/axis.py [seconds=5]
"""
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from obelisk import device, hidraw, protocol, settings

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
fd = hidraw.open_device(hidraw.find_device())
try:
    rng = protocol.get_value(next(s for s in settings.REGISTRY if s.key == "steering_range"),
                             device.Device(fd).read_page(3, 3.0))
    samples = []
    end = time.monotonic() + secs
    last = 0.0
    while time.monotonic() < end:
        r = hidraw.read_report(fd, 0.1)
        v = protocol.parse_axis(r) if r else None
        if v is not None:
            samples.append(v)
            if time.monotonic() - last > 0.5:
                last = time.monotonic()
                deg = samples[-1] * (rng / 2) / 32767
                print(f"counts={samples[-1]:7d}  angle={deg:8.1f} deg  (steering range {rng})", flush=True)
    if samples:
        print(f"median counts={statistics.median(samples):.0f}  samples={len(samples)}")
finally:
    os.close(fd)
