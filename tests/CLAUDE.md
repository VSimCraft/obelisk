# tests/

## Files

| File                | What                                                                  | When to read                                                   |
| ------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------- |
| `test_protocol.py`  | Byte-exact tests against captured reports, axis parsing, fake wheel   | Changing `protocol.py` or `device.py`, adding a setting        |
| `test_startup.py`   | Apply policy, Max Torque once per connection, active profile, ranges  | Changing `apply_values`, profile activation, setting limits    |
| `test_filter.py`    | Overall Filter inversion and range                                    | Changing the filter scaling                                    |
| `test_center.py`    | Axis counts to degrees, `read_position` queue draining                | Changing `center.py` or `Device.read_position`                 |
| `test_profiles.py`  | Profile storage, format validation, name sanitising                   | Changing `profiles.py`, import/export                          |
| `test_hidraw.py`    | Unplug errnos map to `DeviceLost`, other errors to `DeviceError`      | Changing `hidraw.py` error handling, reconnect logic           |
| `test_wheels.py`    | Wheel database lookup by USB ID                                       | Changing `wheels.py` or `wheels.ini`                           |
| `test_gui_smoke.py` | Builds the real `MainWindow` with no device; skipped without a display | Changing `gui.py` or `widgets.py`, checking a GUI refactor    |

## Test

`python -m unittest discover -s tests`
