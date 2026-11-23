"""ISO 13616 format and MOD-97 check for the countries used by our fixtures."""

import re

# These are format definitions, not configurable business thresholds.
FORMATS = {"DE": r"DE[0-9]{20}", "GB": r"GB[0-9]{2}[A-Z]{4}[0-9]{14}"}


def is_valid_iban(value: str) -> bool:
    compact = "".join(value.split()).upper()
    pattern = FORMATS.get(compact[:2])
    if pattern is None or not re.fullmatch(pattern, compact):
        return False
    rearranged = compact[4:] + compact[:4]
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    return int(digits) % 97 == 1
