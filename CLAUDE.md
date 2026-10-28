# obelisk

Linux settings tool (`obelisk`, GTK4 + libadwaita) for the VNM Xtreme 32 Nm direct-drive wheelbase.

## Files

| File         | What                                                         | When to read                                         |
| ------------ | ------------------------------------------------------------ | ---------------------------------------------------- |
| `README.md`  | User guide: setup, controls, profiles, known jstest deadzone | Installing, using, or documenting user-facing change |
| `.gitignore` | Ignores caches, local captures/logs, graphify and agent dirs | Adding files that must not be committed              |
| `LICENSE`    | Project license text                                         | Checking licensing terms before redistributing code  |
| `pyproject.toml` | Package metadata (PyPI name `obelisk-ffb`), entry point, package data | Changing version, dependencies, or what ships in the wheel |
| `CHANGELOG.md` | Release notes per version                                  | Preparing a release                                  |
| `.github/workflows/release.yml` | Tag-triggered test, build, PyPI publish, GitHub Release | Changing the release process                  |

## Subdirectories

| Directory    | What                                                          | When to read                                                    |
| ------------ | ------------------------------------------------------------- | --------------------------------------------------------------- |
| `obelisk/`    | The application package (protocol, device, profiles, GUI)     | Adding settings, changing device I/O, profile or GUI behavior   |
| `tests/`     | Unit tests with captured bytes, plus a GTK smoke test         | Adding or fixing tests, verifying a change                      |
| `tools/`     | USB capture parser and live axis monitor (dev only)           | Decoding new protocol behavior, checking axis output            |
| `docs/`      | Wire protocol decoded from USB captures                       | Understanding report layout, adding a setting                   |
| `packaging/` | nfpm config and launcher for the .deb/.rpm, Arch PKGBUILD | Changing how system packages are built or what they install |
| `obelisk/data/` | udev rule and desktop entry template, shipped as package data | Fixing hidraw permissions, changing the menu entry         |

## Build

`python -m build` (setuptools; wheel and sdist in `dist/`). Runtime needs system PyGObject, GTK4 and libadwaita; they are deliberately not declared as dependencies.

## Test

`python -m unittest discover -s tests`

## Development

Run the app: `python -m obelisk`. Apply the active profile without a window: `obelisk --apply`. udev rule: `obelisk --print-udev-rule | sudo tee /etc/udev/rules.d/70-vnm-direct-drive.rules`. Menu entry: `obelisk --install-desktop`.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- A committed graphify-out/graph.json is rewritten whole on every build, so a large diff to it in a pull request is expected. Do not flag it as churn or suggest skipping the graph rebuild or its hooks.
