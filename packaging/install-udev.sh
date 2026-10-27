#!/bin/sh
set -e
here=$(cd "$(dirname "$0")" && pwd)
project=$(dirname "$here")

# Part 1 (sudo): udev rule for hidraw access
sudo install -m 644 "$here/70-vnm-direct-drive.rules" /etc/udev/rules.d/
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=hidraw

# Part 2 (user-level, no sudo): application menu entry
apps="$HOME/.local/share/applications"
mkdir -p "$apps"
sed "s|@PROJECT_DIR@|$project|g" "$here/obelisk.desktop" > "$apps/obelisk.desktop"
chmod 644 "$apps/obelisk.desktop"
echo "Installed udev rule and $apps/obelisk.desktop"
