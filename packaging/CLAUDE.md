# packaging/

System packages built by the release workflow. The package is pure Python, so the `.deb`/`.rpm` are arch-independent.

## Files

| File             | What                                                                                | When to read                                        |
| ---------------- | ----------------------------------------------------------------------------------- | --------------------------------------------------- |
| `build.sh`       | Unpacks the wheel from `dist/`, stages the desktop file, runs nfpm for deb and rpm   | Building packages locally, changing staged files    |
| `nfpm.yaml`      | Package metadata, install paths, per-format dependencies                             | Changing dependencies or what the packages install  |
| `launcher`       | `/usr/bin/obelisk`: puts `/usr/share/obelisk` on `sys.path`, calls `obelisk.cli`     | Changing where the package files are installed      |
| `udev-reload.sh` | post-install/remove script: reloads udev and re-triggers hidraw                      | Changing install-time device handling               |
| `arch/PKGBUILD`  | Arch package built from the tag tarball; release workflow stamps pkgver and checksum | Changing the Arch package                           |

## Invariants

- The `.deb`/`.rpm` keep the code in `/usr/share/obelisk` and use `/usr/bin/python3`, so there is no per-distribution site-packages path. GTK bindings only exist for the system Python.
- Local build: `python -m build --wheel`, then `packaging/build.sh` with `nfpm` on PATH. Output goes to `dist/`.
