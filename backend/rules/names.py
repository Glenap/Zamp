"""Deterministic name normalization and fuzzy similarity."""

import re
import unicodedata
from rapidfuzz.fuzz import ratio


def normalize_name(value):
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", "".join(c for c in decomposed if not unicodedata.combining(c)).lower()).split())


def name_score(left, right):
    a, b = normalize_name(left), normalize_name(right)
    return ratio(a, b) / 100 if a and b else 0.0
