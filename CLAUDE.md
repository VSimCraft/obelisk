# obelisk

Linux settings tool (`obelisk`, GTK4 + libadwaita) for the VNM Xtreme 32 Nm direct-drive wheelbase.

## Files

| File         | What                                                         | When to read                                         |
| ------------ | ------------------------------------------------------------ | ---------------------------------------------------- |
| `README.md`  | User guide: setup, controls, profiles, known jstest deadzone | Installing, using, or documenting user-facing change |
| `.gitignore` | Ignores caches, local captures/logs, graphify and agent dirs | Adding files that must not be committed              |

## Subdirectories

| Directory    | What                                                          | When to read                                                    |
| ------------ | ------------------------------------------------------------- | --------------------------------------------------------------- |
| `obelisk/`    | The application package (protocol, device, profiles, GUI)     | Adding settings, changing device I/O, profile or GUI behavior   |
| `tests/`     | Unit tests with captured bytes, plus a GTK smoke test         | Adding or fixing tests, verifying a change                      |
| `tools/`     | USB capture parser and live axis monitor (dev only)           | Decoding new protocol behavior, checking axis output            |
| `docs/`      | Wire protocol decoded from USB captures                       | Understanding report layout, adding a setting                   |
| `packaging/` | udev rule, install script, desktop entry                      | Fixing hidraw permissions, changing installation                |

## Build

No build step (pure Python 3, PyGObject with GTK4 and libadwaita).

## Test

`python -m unittest discover -s tests`

## Development

Run the app: `python -m obelisk`. Apply the active profile without a window: `python -m obelisk --apply`. One-time hidraw access setup: `sh packaging/install-udev.sh`.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- A committed graphify-out/graph.json is rewritten whole on every build, so a large diff to it in a pull request is expected. Do not flag it as churn or suggest skipping the graph rebuild or its hooks.
