"""German VAT identifier MOD 11,10 check, without registry verification."""

import re


def de_vat_check_digit(body: str) -> str:
    if not re.fullmatch(r"[0-9]{8}", body):
        raise ValueError("German VAT body must contain eight digits")
    product = 10
    for digit in body:
        subtotal = (int(digit) + product) % 10 or 10
        product = (2 * subtotal) % 11
    return str((11 - product) % 10)


def is_valid_de_vat(value: str) -> bool:
    return bool(re.fullmatch(r"DE[1-9][0-9]{8}", value)) and de_vat_check_digit(value[2:10]) == value[-1]
