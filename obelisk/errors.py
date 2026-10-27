"""Error types shared across obelisk."""


class VnmError(Exception):
    """Base for expected, user-reportable failures."""


class SettingError(VnmError):
    """A setting value is invalid: out of range or not representable."""
