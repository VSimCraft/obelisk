# Obelisk

Linux settings tool for the **VNM Xtreme 32 Nm** direct-drive wheelbase (USB `0483:a3d5`), replacing the
Windows-only VNM SimCenter for everyday settings. GTK4 + libadwaita (PyGObject), standard library otherwise.

## Setup
```
sh packaging/install-udev.sh     # one time: hidraw access rule (sudo) + app-menu entry
python -m obelisk                 # start the GUI (or use the "Obelisk" menu entry)
```

## What it controls
Steering Range, Overall Gain, Overall Filter, Damper / Friction / Inertia / Spring Gain, Max Torque Mode,
and a Center button (the wheel's current angle becomes zero). The Basic page also shows the live wheel angle and the
resulting torque in Nm (wheel maximum from `obelisk/wheels.ini` x Overall Gain %, halved when Max Torque Mode is off).
Telemetry, FFB mode, firmware update and Calibrate are intentionally not implemented.

## Profiles and what the wheelbase remembers
**The wheelbase does not keep what we write**; it powers up with its own stored values (currently 360 / 90 / 293 ...).
So Obelisk keeps your values itself, as profiles in `~/.config/obelisk/profiles/`:
- The **active profile** is applied automatically every time the wheelbase connects (only values that differ are written).
- Loading a profile makes it active. **Save to profile** stores the current values into the active one
  (it creates "Default" if none is active). Import/Export use plain JSON files.
- `python -m obelisk --apply` applies the active profile without opening a window.
- Max Torque Mode cannot be read back from the wheelbase, so the switch shows what was last sent; it is stored in profiles.
- Center is a volatile offset on the wheelbase. It is not stored in profiles.

## Notes
- `docs/protocol.md` is the wire protocol as decoded from USB captures (raw captures are not distributed; `capture/...` names cited in the docs and code refer to them), including what did not work.
- `tools/usbmon_parse.py` reads usbmon text and USBPcap `.pcapng` captures; `tools/axis.py` prints the live steering position.
- Tests: `python -m unittest discover -s tests`.

## Joystick deadzone in `jstest`
The kernel reports a deadzone ("flat") of 4095 on the steering axis, which `/dev/input/js*` (jstest, legacy joydev apps)
applies: about +/-56 deg around center at a 900 deg range. Games using evdev/SDL are not affected the same way.
