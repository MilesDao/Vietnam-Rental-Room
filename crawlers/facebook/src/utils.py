"""Pure, Facebook-agnostic helpers: normalization, hashing, JSONL I/O, logging.

Nothing in this module touches a browser or Facebook DOM. Everything here is
deterministic and unit-testable offline. DOM-specific heuristics live in
``parser.py`` only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse, urlunparse

# ---------------------------------------------------------------------------
# Count parsing
# ---------------------------------------------------------------------------

# Suffix multipliers seen on Facebook counts across locales.
#   K / N (Vietnamese "nghìn")            -> thousand
#   M / TR (Vietnamese "triệu")           -> million
#   B / T / TY (Vietnamese "tỷ")          -> billion
# We match longest suffixes first so "TR"/"TY" win over a bare "T".
_COUNT_SUFFIXES: list[tuple[str, int]] = [
    ("TR", 1_000_000),
    ("TY", 1_000_000_000),
    ("K", 1_000),
    ("N", 1_000),
    ("M", 1_000_000),
    ("B", 1_000_000_000),
    ("T", 1_000_000_000),
]

_COUNT_NUMBER_RE = re.compile(r"[-+]?\d[\d.,]*")


def parse_count(value: str | int | float | None) -> int | None:
    """Normalize a human-readable count into an integer.

    Examples::

        "1.2K"  -> 1200
        "3K"    -> 3000
        "2.5M"  -> 2500000
        "1,234" -> 1234
        "1,2K"  -> 1200   # Vietnamese decimal comma
        "12 lượt bình luận" -> 12

    Returns ``None`` when no number can be reliably extracted. Never guesses.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip()
    if not text:
        return None

    match = _COUNT_NUMBER_RE.search(text)
    if not match:
        return None
    number_str = match.group(0)

    # Detect a multiplier suffix immediately following the number (allowing a
    # space), case-insensitively. e.g. "1.2 K", "2,5Tr".
    remainder = text[match.end():].strip().upper()
    multiplier = 1
    for suffix, mult in _COUNT_SUFFIXES:
        if remainder.startswith(suffix):
            multiplier = mult
            break

    if multiplier != 1:
        # With a multiplier, a single '.' or ',' is a decimal separator.
        # Normalize both to '.' and parse as float. ("1,2K" -> 1.2 * 1000)
        normalized = number_str.replace(",", ".")
        # If multiple dots remain (e.g. thousands grouping like "1.234K"),
        # treat all but the last as grouping separators.
        if normalized.count(".") > 1:
            head, _, tail = normalized.rpartition(".")
            normalized = head.replace(".", "") + "." + tail
        try:
            return int(round(float(normalized) * multiplier))
        except ValueError:
            return None

    # No multiplier: this is a plain integer count. Separators ('.' or ',')
    # are thousands groupings and can be stripped. ("1,234" / "1.234" -> 1234)
    digits = re.sub(r"[.,\s]", "", number_str)
    if not digits or digits in {"-", "+"}:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# URL / permalink normalization
# ---------------------------------------------------------------------------

# Canonical host we normalize every Facebook URL to, so the same post reached
# via web./m./www. hosts dedupes to one key.
_CANONICAL_HOST = "www.facebook.com"

# Query params that are pure tracking / view-state noise and must be dropped
# before a URL is used as an identity key.
_TRACKING_PARAM_PREFIXES = ("__", "fref", "ref", "notif", "comment_", "hc_")

# Permalink id patterns, tried in order.
_POST_ID_PATTERNS = [
    re.compile(r"/groups/[^/]+/posts/(\d+)"),
    re.compile(r"/groups/[^/]+/permalink/(\d+)"),
    re.compile(r"/permalink/(\d+)"),
    re.compile(r"/posts/(\d+)"),
    re.compile(r"[?&]story_fbid=(\d+)"),
    re.compile(r"[?&]fbid=(\d+)"),
    re.compile(r"multi_permalinks=(\d+)"),
]


def normalize_url(url: str | None) -> str | None:
    """Canonicalize a Facebook URL for use as a dedup key.

    - forces scheme https and host ``www.facebook.com``
    - strips query string and fragment (tracking noise, view-state)
    - collapses a trailing slash

    Returns ``None`` for falsy/invalid input.
    """
    if not url:
        return None
    url = url.strip()
    if not url:
        return None

    # Make protocol-relative and path-only hrefs absolute so urlparse works.
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = "https://" + _CANONICAL_HOST + url

    try:
        parts = urlparse(url)
    except ValueError:
        return None

    host = parts.netloc.lower()
    if host.endswith("facebook.com"):
        host = _CANONICAL_HOST
    if not host:
        return None

    path = parts.path.rstrip("/") or "/"

    # Query is dropped entirely for identity; story_fbid etc. are captured
    # separately via extract_post_id when the path lacks an id.
    normalized = urlunparse(("https", host, path, "", "", ""))
    return normalized


def extract_post_id(url: str | None) -> str | None:
    """Extract a numeric Facebook post id from a permalink, if reliably present.

    Returns ``None`` when no known pattern matches. Never invents an id.
    """
    if not url:
        return None
    for pattern in _POST_ID_PATTERNS:
        m = pattern.search(url)
        if m:
            return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

# Trailing UI affordances that Facebook sometimes leaves glued to post text.
_TRAILING_UI_TOKENS = (
    "See more",
    "See More",
    "Xem thêm",
    "See translation",
    "Xem bản dịch",
)


def normalize_text(text: str | None) -> str | None:
    """Normalize post text while preserving Unicode, emoji, and line breaks.

    - unifies CRLF/CR to LF
    - trims trailing whitespace on each line
    - collapses 3+ blank lines to a single blank line
    - strips a dangling "See more"/"Xem thêm" affordance if present
    - strips leading/trailing whitespace overall

    Returns ``None`` for falsy input.
    """
    if text is None:
        return None
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Drop a trailing affordance token that leaked into the text.
    stripped = text.rstrip()
    for token in _TRAILING_UI_TOKENS:
        if stripped.endswith(token):
            stripped = stripped[: -len(token)].rstrip()
    text = stripped

    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    return text or None


def generate_fallback_hash(text: str | None, timestamp_text: str | None) -> str:
    """SHA256 over normalized text + timestamp text; the last-resort dedup key."""
    basis = f"{normalize_text(text) or ''}\x1f{(timestamp_text or '').strip()}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# JSONL I/O and dedup key building
# ---------------------------------------------------------------------------


def load_jsonl(path: str | Path) -> list[dict]:
    """Load a JSONL file into a list of dicts, skipping blank/corrupt lines."""
    p = Path(path)
    if not p.exists():
        return []
    records: list[dict] = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                # Tolerate a partially-written trailing line from a crash.
                continue
    return records


def post_identity_key(record: dict) -> str:
    """Return the strongest available dedup key for a record.

    Order: post_url -> post_id -> fallback hash. Mirrors the crawl-time
    dedup order so a reloaded record maps to the same key it was stored under.
    """
    if record.get("post_url"):
        return f"url:{record['post_url']}"
    if record.get("post_id"):
        return f"id:{record['post_id']}"
    return "hash:" + generate_fallback_hash(
        record.get("text"), record.get("timestamp_text")
    )


def build_known_keys(records: Iterable[dict]) -> set[str]:
    """Build the set of known identity keys from already-collected records."""
    return {post_identity_key(r) for r in records}


# ---------------------------------------------------------------------------
# Logging + pacing
# ---------------------------------------------------------------------------


def setup_logger(log_path: str | Path, name: str = "crawler") -> logging.Logger:
    """Configure a logger writing to both the log file and stderr."""
    logger = logging.getLogger(name)
    if logger.handlers:  # idempotent across restarts within one process
        return logger
    logger.setLevel(logging.INFO)

    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = RotatingFileHandler(
        log_path, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    return logger


def human_delay(min_seconds: float, max_seconds: float) -> float:
    """Sleep a randomized human-readable delay; return the seconds slept."""
    lo, hi = min(min_seconds, max_seconds), max(min_seconds, max_seconds)
    seconds = random.uniform(lo, hi)
    time.sleep(seconds)
    return seconds
