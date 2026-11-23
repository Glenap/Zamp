"""ABA routing-number format and weighted checksum; not a directory lookup."""

import re


def is_valid_aba(value: str) -> bool:
    if not re.fullmatch(r"[0-9]{9}", value) or value == "000000000":
        return False
    prefix = int(value[:2])
    if not (0 <= prefix <= 12 or 21 <= prefix <= 32 or 61 <= prefix <= 72 or prefix == 80):
        return False
    return sum(int(digit) * weight for digit, weight in zip(value, (3, 7, 1) * 3)) % 10 == 0
