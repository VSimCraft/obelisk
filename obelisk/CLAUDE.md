# obelisk/

## Files

| File          | What                                                              | When to read                                                          |
| ------------- | ----------------------------------------------------------------- | --------------------------------------------------------------------- |
| `README.md`   | Layering, threading model, design decisions, invariants           | Understanding the architecture, before changing locking or apply flow |
| `cli.py`      | Entry point: `--apply`, `--version`, `--print-udev-rule`, `--install-desktop`, else GUI | Changing startup behavior or CLI flags                                |
| `__main__.py` | `python -m obelisk` shim calling `cli.main`                       | -                                                                     |
| `data/`       | udev rule and desktop entry template (`@EXEC@`), package data      | Changing device permissions or the menu entry                         |
| `settings.py` | Registry of settings: page, offset, range, scaling                | Adding or changing a setting, fixing a range                          |
| `protocol.py` | Pure byte builders/parsers for vendor reports, axis report decode | Changing wire format handling, adding a page, decoding a report       |
| `device.py`   | `Device`: locked page read/write, apply, center, position         | Debugging device I/O, changing apply policy or timeouts               |
| `hidraw.py`   | hidraw discovery, open, report read/write, `DeviceError`          | Debugging connection or permission problems                           |
| `wheels.py`   | Loads `wheels.ini`: wheelbase name, max torque per USB ID         | Supporting another wheelbase, changing what the header shows          |
| `wheels.ini`  | Wheelbase database keyed by USB ID (`vendor:product`)             | Adding a wheelbase or a per-wheel field                               |
| `profiles.py` | Profile JSON storage, active-profile pointer, name rules          | Changing the profile format, import/export, config location           |
| `center.py`   | Axis counts to degrees conversion                                 | Changing the wheel-angle display                                      |
| `gui.py`      | `MainWindow`, `App`: pages, connect/poll logic, profile UI        | Changing UI layout, connection handling, profile actions              |
| `widgets.py`  | `Worker` thread, `confirm` dialog, `Control` (spin + scale row)   | Changing threading of GUI actions, dialogs, or the setting rows       |
| `__init__.py` | `__version__`, the single source of the package version            | Releasing                                                             |
