# Obelisk

## Overview

Settings tool for the VNM direct-drive wheelbase, talking to its vendor HID channel over `/dev/hidraw*`. Games keep using the standard HID/PID force-feedback interface; this package never writes to it. All writes use vendor report ID `0x14`.

## Architecture

```
settings (registry)  <-  protocol (pure bytes)  <-  device (locked I/O)  ->  hidraw (fd)
                                                         ^
profiles (JSON on disk)  ---------------------------- gui / widgets / cli
```

- `settings` + `protocol` do no I/O, so the wire format is unit-testable against captured bytes.
- GUI actions run on one `Worker` thread; results return to the GTK thread via `GLib.idle_add`. The GUI thread never blocks on the device.
- `cli --apply` imports GTK lazily so the active profile can be applied headless (login scripts, no display).
- Settings live in numbered pages (3, 5, 8). A page is read, patched and written back whole.

## Design Decisions

- **Profiles are stored on the host, not the wheelbase.** The wheelbase does not keep what we write and powers up with its own stored values, so the active profile is re-applied on every connect. `apply_values` writes only values that differ.
- **Read-modify-write per page** preserves bytes we do not understand (for example page 8, which never changed in captures).
- **Max Torque Mode is write-only.** The wheel cannot report it, so `Device.max_torque` records what was last sent. It is sent once per connection, and again when the wanted mode changes. The GUI switch shows "last sent", not device state.
- **Center is a volatile offset** on the wheelbase and is deliberately not part of profiles.
- **Axis stream:** the wheel emits about 1000 axis reports/s (report ID `0x01`). Replies to page reads are interleaved with them, so `read_page` drops the queue before sending, and `read_position` keeps only the newest axis report (capped at 2048 reads) instead of returning the oldest queued one.
- **Overall Filter is inverted on the wire** (`wire = 501 - value`), except raw 0, which is UI 0.

## Invariants

- `Device._lock` is a plain `Lock`. `read_page` and `write_page` do not take it: callers (`set_setting`, `read_all`, `apply_values`) hold it for the whole read-modify-write. Calling a public setter from inside one that holds the lock deadlocks.
- Expected failures derive from `errors.VnmError` (`DeviceError`, `ProfileError`, `SettingError`); `ValueError` is reserved for programming errors.
- Out-of-range values must be rejected before any byte is written (`apply_values` validates first).
- `Setting.page` is a page number, not a USB report ID; the report-ID constants live in `protocol`.
- Only `profiles.py` knows the profile file format and the profile-name rule. GUI import/export go through `parse_profile`, `dump_profile` and `sanitize_name`.
- GTK may be imported only by `gui.py` and `widgets.py`.
