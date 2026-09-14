"""Text normalization for listing free text (title, description, address).

Pure functions of a string -- no network, no pandas -- unit-testable the same
way src/parse/vn_text.py is. Price/area parsing already happens at crawl time
(src/parse/vn_text.py); this module covers the rest of docs/PLAN.md Phase 3's
"Text normalization" checklist item.
"""
from __future__ import annotations

import re
import unicodedata

# Built from code points rather than literal escapes in this file, so the
# ranges can't get mangled by editors/tools that "helpfully" decode \\uXXXX.
_CONTROL_RANGES = [(0, 8), (11, 12), (14, 31), (127, 127)]
_DECORATIVE_RANGES = [
    (0x1F300, 0x1FAFF),  # pictographs / emoji
    (0x2600, 0x27BF),    # misc symbols, dingbats
    (0x1F1E6, 0x1F1FF),  # regional indicator letters
    (0x2500, 0x25FF),    # box drawing / geometric shapes used as decoration
]


def _char_class(ranges: list[tuple[int, int]]) -> str:
    chars = "".join(chr(c) for lo, hi in ranges for c in range(lo, hi + 1))
    return "[" + re.escape(chars) + "]"


_CONTROL_RE = re.compile(_char_class(_CONTROL_RANGES))
_DECORATIVE_RE = re.compile(_char_class(_DECORATIVE_RANGES) + "+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_INLINE_WHITESPACE_RE = re.compile(r"[ \t]+")


def normalize_text(s: str | None) -> str | None:
    """NFC-normalize, strip control chars/emoji/decorative glyphs, collapse whitespace.

    Keeps Vietnamese diacritics -- this is the display copy, not the matching
    copy (see ascii_fold).
    """
    if s is None:
        return None
    t = unicodedata.normalize("NFC", s)
    t = _DECORATIVE_RE.sub("", t)
    t = _CONTROL_RE.sub("", t)
    t = _INLINE_WHITESPACE_RE.sub(" ", t)
    lines = [line.strip() for line in t.split("\n")]
    t = "\n".join(lines)
    t = _BLANK_LINES_RE.sub("\n\n", t)
    return t.strip()


def ascii_fold(s: str | None) -> str | None:
    """Strip Vietnamese diacritics to lowercase ASCII, for matching only (not display).

    NFKD decomposition handles most diacritics, but "d with stroke" is a
    distinct codepoint (not a base letter + combining mark), so it needs an
    explicit substitution first.
    """
    if s is None:
        return None
    t = s.replace("đ", "d").replace("Đ", "D")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return t.lower()
