# packaging/

## Files

| File                         | What                                                                  | When to read                                                |
| ---------------------------- | --------------------------------------------------------------------- | ----------------------------------------------------------- |
| `install-udev.sh`            | Installs the udev rule (sudo) and the app-menu entry for the user     | Changing installation, debugging missing hidraw access      |
| `70-vnm-direct-drive.rules`  | udev rule giving the logged-in user hidraw access to `0483:a3d5`      | Changing device permissions or supporting another device ID |
| `obelisk.desktop`             | Desktop entry template; `@PROJECT_DIR@` is substituted on install     | Changing the menu entry, name, or categories                |

## Install

`sh packaging/install-udev.sh`
