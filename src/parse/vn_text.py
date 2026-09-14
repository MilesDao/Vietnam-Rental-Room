"""Small, dependency-free parsers for Vietnamese listing text.

Shared by every site parser (not mogi-specific) since "3,5 triệu/tháng"-style
numbers show up across all Tier-1 sources.
"""
from __future__ import annotations

import re

_NEGOTIABLE_WORDS = ("thỏa thuận", "thoả thuận", "thương lượng", "liên hệ")

# "2 triệu", "2tr", "2,5tr", "5 triệu 500 nghìn", "3.500.000", "350 nghìn", "3tr5"
_TRIEU_NGHIN_RE = re.compile(
    r"(?P<trieu>\d+(?:[.,]\d+)?)\s*(?:triệu|tr)\b(?:\s*(?P<nghin_after_trieu>\d+)(?!\S))?"
    r"|(?P<nghin_only>\d+(?:[.,]\d+)?)\s*(?:nghìn|k)\b",
    re.IGNORECASE,
)
_TR_SHORTHAND_RE = re.compile(r"(?P<whole>\d+)\s*tr\s*(?P<frac>\d)\b", re.IGNORECASE)
_PLAIN_VND_RE = re.compile(r"(?P<num>\d{1,3}(?:[.,]\d{3}){2,})\s*(?:đ|vnd|d)?\b", re.IGNORECASE)


def parse_price_vnd(text: str | None) -> tuple[float | None, bool]:
    """Return (price_vnd_month, is_negotiable). None if not parseable."""
    if not text:
        return None, False
    t = text.strip().lower()
    if any(w in t for w in _NEGOTIABLE_WORDS):
        return None, True

    m = _TR_SHORTHAND_RE.search(t)  # "3tr5" == 3.5 trieu
    if m:
        return (float(m.group("whole")) + float(m.group("frac")) / 10) * 1_000_000, False

    total = 0.0
    matched = False
    for m in _TRIEU_NGHIN_RE.finditer(t):
        matched = True
        if m.group("trieu"):
            total += float(m.group("trieu").replace(",", ".")) * 1_000_000
            if m.group("nghin_after_trieu"):
                total += float(m.group("nghin_after_trieu")) * 1_000
        elif m.group("nghin_only"):
            total += float(m.group("nghin_only").replace(",", ".")) * 1_000
    if matched and total > 0:
        return total, False

    m = _PLAIN_VND_RE.search(t)
    if m:
        return float(m.group("num").replace(".", "").replace(",", "")), False

    return None, False


_AREA_RE = re.compile(r"(?P<num>\d+(?:[.,]\d+)?)\s*m")


def parse_area_m2(text: str | None) -> float | None:
    if not text:
        return None
    m = _AREA_RE.search(text.lower())
    if not m:
        return None
    return float(m.group("num").replace(",", "."))
