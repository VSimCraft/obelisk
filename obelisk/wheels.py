"""Wheelbase database (`wheels.ini`), keyed by USB ID."""
import configparser
from dataclasses import dataclass
from pathlib import Path

DB_PATH = Path(__file__).with_name("wheels.ini")


@dataclass(frozen=True)
class Wheel:
    usb_id: str
    name: str
    max_torque_nm: int


def load(path: Path = DB_PATH) -> dict[str, Wheel]:
    parser = configparser.ConfigParser()
    with open(path) as f:
        parser.read_file(f)
    return {
        usb_id.lower(): Wheel(usb_id.lower(), section["name"], section.getint("max_torque_nm"))
        for usb_id, section in parser.items() if usb_id != parser.default_section
    }


def lookup(usb_id: str) -> Wheel | None:
    return load().get(usb_id.lower())
