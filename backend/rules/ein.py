"""EIN display-format check. EINs have no public checksum."""

import re


def is_valid_ein(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9]{2}-[0-9]{7}", value)) and not value.startswith("00-")
