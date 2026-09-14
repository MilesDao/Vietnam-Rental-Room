"""Salted hashing for anything that identifies a person (phone, poster id).

Used for every source, not just the Tier-2 social scrapers: the canonical
schema never stores a raw phone number or poster identity.
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
from pathlib import Path

_SALT_FILE = Path(__file__).resolve().parents[2] / ".project_salt"


def _resolve_salt() -> str:
    """PROJECT_SALT env var, else a persisted repo-local salt, else generate one.

    The salt MUST stay identical for the whole corpus: `phone_hash` is the
    strongest cross-source dedupe key (docs/PLAN.md Phase 3), and re-salting
    silently makes rows from different runs un-joinable. Crawls run for days
    and resume across shells, so relying on an env var being re-exported every
    time is a data-integrity footgun -- we persist one instead. The file is
    gitignored; delete it to rotate (and re-parse the raw HTML afterwards).
    """
    env = os.environ.get("PROJECT_SALT")
    if env:
        return env
    if _SALT_FILE.exists():
        salt = _SALT_FILE.read_text(encoding="utf-8").strip()
        if salt:
            return salt
    salt = secrets.token_hex(16)
    _SALT_FILE.write_text(salt, encoding="utf-8")
    logging.getLogger(__name__).warning(
        "PROJECT_SALT unset -- generated a persistent salt at %s", _SALT_FILE
    )
    return salt


_SALT = _resolve_salt()


def hash_value(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256((value + _SALT).encode("utf-8")).hexdigest()[:16]


def phone_prefix(phone: str | None, n: int = 4) -> str | None:
    """Carrier-identifying prefix only; never keep the full number."""
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    return digits[:n] or None
