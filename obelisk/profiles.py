"""JSON profiles under $XDG_CONFIG_HOME/obelisk (default ~/.config/obelisk)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .errors import VnmError
from .settings import Values

_NAME_CHARS = "A-Za-z0-9_ -"
NAME_RE = re.compile(rf"[{_NAME_CHARS}]{{1,64}}")


class ProfileError(VnmError):
    pass


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "obelisk"


def _profiles_dir() -> Path:
    return config_dir() / "profiles"


def _path(name: str) -> Path:
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise ProfileError(f"invalid profile name {name!r}")
    return _profiles_dir() / f"{name}.json"


def sanitize_name(stem: str) -> str:
    return re.sub(rf"[^{_NAME_CHARS}]", "_", stem)[:64] or "imported"


def parse_profile(data) -> Values:
    values = data.get("values") if isinstance(data, dict) else None
    if (data.get("version") != 1 if isinstance(data, dict) else True) or not isinstance(values, dict) \
            or not all(isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool)
                       for k, v in values.items()):
        raise ProfileError("invalid profile format")
    return values


def _read_values(p: Path) -> Values:
    try:
        data = json.loads(p.read_text())
    except FileNotFoundError as e:
        raise ProfileError(f"{p.name} not found") from e
    except (OSError, ValueError) as e:
        raise ProfileError(f"cannot read {p.name}: {e}") from e
    try:
        return parse_profile(data)
    except ProfileError as e:
        raise ProfileError(f"{p.name}: {e}") from e


def dump_profile(values: Values) -> str:
    return json.dumps({"version": 1, "values": values}, indent=2)


def _write(p: Path, values: Values) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(dump_profile(values))
    os.replace(tmp, p)


def list_profiles() -> list[str]:
    d = _profiles_dir()
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.json") if NAME_RE.fullmatch(p.stem))


def load(name: str) -> Values:
    return _read_values(_path(name))


def save(name: str, values: Values) -> None:
    _write(_path(name), dict(values))


def delete(name: str) -> None:
    try:
        _path(name).unlink()
    except FileNotFoundError as e:
        raise ProfileError(f"profile {name!r} not found") from e


def _active_path() -> Path:
    return config_dir() / "active.json"


def get_active() -> str | None:
    """Name of the profile applied on every connect (the wheelbase keeps nothing itself)."""
    p = _active_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError) as e:
        raise ProfileError(f"cannot read {p.name}: {e}") from e
    name = data.get("active") if isinstance(data, dict) else None
    if name is None:
        return None
    _path(name)  # validates the name
    return name


def set_active(name: str | None) -> None:
    if name is not None:
        _path(name)  # validates the name
    p = _active_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps({"active": name}))
    os.replace(tmp, p)


def load_active() -> tuple[str, Values] | None:
    name = get_active()
    return None if name is None else (name, load(name))

