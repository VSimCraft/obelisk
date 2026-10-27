"""Setting registry (basic controls only; source: docs/protocol.md)."""
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    group: str  # "Basic" | "Advanced" | "Game"
    kind: Literal["int", "bool", "enum", "action"]
    min: int
    max: int
    default: int
    step: int
    unit: str
    page: int  # page number (see protocol.PAGE_LEN)
    offset: int  # index into the page payload
    width: int
    scale: float  # value = raw * scale
    choices: tuple[tuple[str, int], ...]
    invert: int | None = None  # if set, wire raw = invert - logical raw (Overall Filter: 501); wire raw 0 is NOT inverted


# Steering Range: SimCenter's slider spans 180-1080 deg (capture/09-ranges.pcapng, NOTES.md);
# the vendor manual (section 2.3) recommends 360-1080 across vehicle types, default 900.
#
# Gains: the manual (sections 2.5, 2.7.1-2.7.4) gives only *recommended* ranges
# (damper 0-20 %, friction/inertia 0-10 %, overall/spring none); the UI scale is
# percent 0..100, stored raw 0..10000 (scale 0.01). Defaults = initial values in
# docs/protocol.md.
def _gain(key, label, page, offset, default):
    return Setting(
        key=key, label=label, group="Basic", kind="int",
        min=0, max=100, default=default, step=1, unit="%",
        page=page, offset=offset, width=2, scale=0.01, choices=(),
    )


REGISTRY: tuple[Setting, ...] = (
    Setting(
        key="steering_range", label="Steering Range", group="Basic", kind="int",
        min=180, max=1080, default=900, step=1, unit="°",
        page=3, offset=8, width=2, scale=1, choices=(),
    ),
    _gain("overall_gain", "Overall Gain", 3, 22, 90),
    # Overall Filter: page 3 idx 14, le16, wire = 501 - value (capture 02-filter.pcapng:
    # typed 100/300/470/276 -> 0x0191/0x00c9/0x001f/0x00e1). Manual gives only a
    # recommended range 300-470; SimCenter's slider spans 0..500 (reported by the user).
    # invert=501 applies only to nonzero raw: wire 0 is UI 0 and is NOT inverted (protocol.get_value/set_value skip raw == 0).
    Setting(
        key="overall_filter", label="Overall Filter", group="Basic", kind="int",
        min=0, max=500, default=276, step=1, unit="",
        page=3, offset=14, width=2, scale=1, choices=(), invert=501,
    ),
    _gain("damper_gain", "Damper Gain", 5, 2, 3),
    _gain("friction_gain", "Friction Gain", 5, 6, 2),
    _gain("inertia_gain", "Inertia Gain", 5, 10, 0),
    _gain("spring_gain", "Spring Gain", 5, 14, 0),
)


# Max Torque Mode is a wheelbase command, not a page field (docs/protocol.md, "Windows session"):
# 14 0d 00 ec 00 00 00 00 <0|1>. The wheelbase never reports it, so profiles store the value
# under this key and Device remembers what it last sent.
MAX_TORQUE_KEY = "max_torque_mode"

# Setting key -> UI value (whole numbers: percent, degrees, filter steps).
Values = dict[str, int]

