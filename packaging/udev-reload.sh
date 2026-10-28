#!/bin/sh
# Apply the udev rule to an already plugged-in wheelbase without a replug.
if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload || true
    udevadm trigger --subsystem-match=hidraw --action=add || true
fi
exit 0
