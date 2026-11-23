"""IFSC structure only; IFSCs do not have a check digit."""

import re


def is_valid_ifsc(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", value))
