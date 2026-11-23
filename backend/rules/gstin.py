"""GSTIN format plus base-36 Luhn checksum; no registration lookup."""

import re

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_check_digit(body: str) -> str:
    if not re.fullmatch(r"[0-9A-Z]{14}", body):
        raise ValueError("GSTIN body must contain 14 uppercase alphanumeric characters")
    total = 0
    factor = 2
    # Fold each product back into base 36, alternating weights right-to-left.
    for character in reversed(body):
        product = ALPHABET.index(character) * factor
        total += product // 36 + product % 36
        factor = 3 - factor
    return ALPHABET[(36 - total % 36) % 36]


def is_valid_gstin(value: str) -> bool:
    pattern = r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]"
    return bool(
        re.fullmatch(pattern, value)
        and 1 <= int(value[:2]) <= 38
        and gstin_check_digit(value[:14]) == value[-1]
    )
