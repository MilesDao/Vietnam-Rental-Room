"""One command that turns the unified branch data into the file the recommender reads.

    python -m src.recsys.prepare        # ~2 min; Nominatim answers come from the cache after the first run

Steps, in order:
1. geo repair      - re-place the fallback-coordinate rows at their ward centroid (regeocode_fallback.repair);
                     the result is also kept as data/unified_hanoi_rentals_geofixed.csv for audit and figures
2. drop            - rows outside Hanoi (city column) and fallback rows whose ward could not be found
                     (their only location was the fake point; most are outside Hanoi)
3. privacy         - contact_phone salted-hashed with src/crawl/pii.py, contact_name dropped, phone numbers
                     written in titles/descriptions replaced by "[SĐT ẩn]";
                     house_type mapped to one label set (sample_schema.canonical_house_type)
4. dates           - posted_at / days_old from posted_at_raw ("Thứ 3, 23:07 08/09/2026"), relative to the
                     newest post in the data (the snapshot date), so the numbers do not drift with time
5. dedup           - cross-platform duplicates marked (sample_schema.mark_duplicates)
6. ML              - missing areas and fair prices from src/recsys/price_model.py (out-of-fold, see there)
Output: data/unified_hanoi_rentals_dedup.csv (the path recommend.load() reads).
"""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from src.clean.link_check import mark_bad_links, parse_images
from src.clean.sample_schema import canonical_house_type, mark_duplicates
from src.crawl.pii import hash_value
from src.recsys import price_model
from src.recsys.regeocode_fallback import repair

ROOT = Path(__file__).resolve().parents[2]
FRESH = ROOT / "data/unified_hanoi_rentals_fresh.csv"   # python -m src.pipelines.merge_fresh
SRC = FRESH if FRESH.exists() else ROOT / "data/unified_hanoi_rentals.csv"
MAX_AGE_DAYS = 180
GEOFIXED = ROOT / "data/unified_hanoi_rentals_geofixed.csv"
OUT = ROOT / "data/unified_hanoi_rentals_dedup.csv"


def hash_phone(value):
    """Raw Vietnamese numbers -> project salted hash; values that are already hashes stay as they are."""
    if isinstance(value, (int, float, np.integer, np.floating)) and not pd.isna(value):
        value = str(int(value))   # a CSV read without dtype=str turns 0912345678 into 912345678
    if not isinstance(value, str):
        return None
    if re.fullmatch(r"[0-9a-f]{16}|[0-9a-f]{64}", value.strip()):   # already hashed (pii.py: 16 hex; Facebook source: SHA-256)
        return value.strip()
    digits = re.sub(r"\D", "", value)
    if re.fullmatch(r"84\d{9}", digits):   # +84 form
        digits = "0" + digits[2:]
    elif re.fullmatch(r"[1-9]\d{8,9}", digits):   # leading 0 lost (CSV read as a number)
        digits = "0" + digits
    return hash_value(digits) if re.fullmatch(r"0\d{9,10}", digits) else None   # never pass through something unrecognised


PHONE_IN_TEXT = re.compile(r"(?<!\d)(?:\+?84|0)[ .-]?\d{2,3}[ .-]?\d{3}[ .-]?\d{3,4}(?!\d)")


def redact_phones(text):
    """Ads print the landlord's number in the text ("LH/Zalo 09xx..."); the app shows that text."""
    return PHONE_IN_TEXT.sub("[SĐT ẩn]", text) if isinstance(text, str) else text


def add_dates(d):
    d = d.copy()
    raw = d.posted_at_raw.astype("string").str.extract(r"(\d{2}/\d{2}/\d{4})")[0]
    d["posted_at"] = pd.to_datetime(raw, format="%d/%m/%Y", errors="coerce")
    d["days_old"] = (d.posted_at.max() - d.posted_at).dt.days
    return d


def drop_stale(d, max_days=MAX_AGE_DAYS):
    """Dated ads older than max_days are probably gone. Undated ads (most sources) are kept: no way to tell."""
    stale = d.days_old > max_days
    print(f"dropped {int(stale.sum())} dated ads older than {max_days} days")
    return d[~stale]


def gate_links(d):
    """Never show a link that cannot open this ad (home/search page, fabricated or shared URL); images -> JSON list."""
    d = d.copy()
    # Facebook is left alone: several rooms legitimately share one group post, and that post is the right link
    d.loc[mark_bad_links(d) & (d.platform != "Facebook"), "listing_url"] = np.nan
    d["image_urls"] = d.image_urls.map(lambda v: json.dumps(parse_images(v), ensure_ascii=False))
    d["image_count"] = d.image_urls.map(lambda v: len(json.loads(v)))
    return d


def drop_unlocatable(d):
    lost = (d.geo_source == "ward_centroid_nominatim") & d.latitude.isna()
    outside = d.city.fillna("Hà Nội") != "Hà Nội"
    print(f"dropped {int(lost.sum())} fallback rows with no findable ward and {int(outside.sum())} rows outside Hanoi")
    return d[~lost & ~outside]


def main():
    d = repair(pd.read_csv(SRC, low_memory=False, dtype={"contact_phone": str, "contact_zalo": str}))
    d.to_csv(GEOFIXED, index=False, encoding="utf-8-sig")
    d = drop_unlocatable(d)
    d["contact_phone"] = d.contact_phone.map(hash_phone)
    d = d.drop(columns=["contact_name"], errors="ignore")
    for c in ["title", "description"]:
        d[c] = d[c].map(redact_phones)
    d["house_type"] = d.house_type.map(canonical_house_type)   # one spelling per type across sources
    d = add_dates(d)
    d = gate_links(drop_stale(d))
    d = mark_duplicates(d, cross_platform=True)
    d = price_model.enrich(d)
    d.to_csv(OUT, index=False, encoding="utf-8-sig")
    n = int(d.duplicate_of.notna().sum())
    print(f"wrote {OUT}: {len(d)} rows, {len(d) - n} distinct rooms ({n} duplicates marked)")


if __name__ == "__main__":
    main()
