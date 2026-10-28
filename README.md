# Obelisk

Linux settings tool for the **VNM Xtreme 32 Nm** direct-drive wheelbase (USB `0483:a3d5`), replacing the
Windows-only VNM SimCenter for everyday settings. GTK4 + libadwaita (PyGObject), standard library otherwise.

## Install
Each [GitHub Release](https://github.com/VSimCraft/obelisk/releases/latest) has native packages. They pull in GTK4, libadwaita and
PyGObject, install the udev rule that lets your user access the wheelbase, and add the app-menu entry. Unplug and replug the
wheelbase if it was connected during install.

- **Debian / Ubuntu**: `sudo apt install ./obelisk_*_all.deb`
- **Fedora / openSUSE**: `sudo dnf install ./obelisk-*.noarch.rpm` (openSUSE: `sudo zypper install ./obelisk-*.noarch.rpm`)
- **Arch**: download the release's `PKGBUILD` into an empty directory, then `makepkg -si`

Remove with your package manager (`apt remove obelisk`, `dnf remove obelisk`, `pacman -R obelisk`).

### With pipx (any distribution)
Obelisk is also on PyPI as `obelisk-ffb`. GTK4, libadwaita and PyGObject come from your distribution, so the pipx environment
must see system packages (`--system-site-packages`) and use the system Python.

1. Install the system libraries and pipx:
   - Arch: `sudo pacman -S python-gobject gtk4 libadwaita python-pipx`
   - Debian / Ubuntu: `sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 pipx`
   - Fedora: `sudo dnf install python3-gobject gtk4 libadwaita pipx`
2. Install Obelisk:
   ```
   pipx install --system-site-packages --python /usr/bin/python3 obelisk-ffb
   ```
3. Allow your user to access the wheelbase (hidraw). This needs root once:
   ```
   obelisk --print-udev-rule | sudo tee /etc/udev/rules.d/70-vnm-direct-drive.rules
   sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=hidraw
   ```
   Unplug and replug the wheelbase if it was connected during this step.
4. Optional app-menu entry (per user): `obelisk --install-desktop`

Upgrade: `pipx upgrade obelisk-ffb`. Uninstall: `pipx uninstall obelisk-ffb`, then
`sudo rm /etc/udev/rules.d/70-vnm-direct-drive.rules ~/.local/share/applications/io.github.vsimcraft.obelisk.desktop`.

If `obelisk` reports missing GTK bindings, the pipx environment is not using the system Python or system site packages:
reinstall with `pipx install --force --system-site-packages --python /usr/bin/python3 obelisk-ffb`.

Start it with `obelisk` or the "Obelisk" menu entry.

## What it controls
Steering Range, Overall Gain, Overall Filter, Damper / Friction / Inertia / Spring Gain, Max Torque Mode,
and a Center button (the wheel's current angle becomes zero). The Basic page also shows the live wheel angle and torque in Nm.
Telemetry, FFB mode, firmware update and Calibrate are not implemented.

## Profiles and what the wheelbase remembers
**The wheelbase does not keep what we write**; it powers up with its own stored values.
So Obelisk keeps your values itself, as profiles in `~/.config/obelisk/profiles/`:
- The **active profile** is applied automatically every time the wheelbase connects (only values that differ are written).
- Loading a profile makes it active. **Save to profile** stores the current values into the active one
  (it creates "Default" if none is active). Import/Export use plain JSON files.
- `obelisk --apply` applies the active profile without opening a window.
- Max Torque Mode cannot be read back, so the switch shows what was last sent; it is stored in profiles. Center is a volatile offset and is not stored.

## Development
Run from a checkout with `python -m obelisk`. Protocol notes: `docs/protocol.md`. Tests: `python -m unittest discover -s tests`.
Releases: bump `__version__` in `obelisk/__init__.py` and `CHANGELOG.md`, then push a tag `vX.Y.Z`; the release workflow
tests, builds, publishes to PyPI (trusted publishing), builds the `.deb`/`.rpm` (`packaging/`) and creates the GitHub Release with
the packages and a stamped `PKGBUILD`.

## Joystick deadzone in `jstest`
The kernel reports a deadzone ("flat") of 4095 on the steering axis, which `/dev/input/js*` (jstest, legacy joydev apps)
applies: about +/-56 deg around center at a 900 deg range. Games using evdev/SDL are not affected the same way.
