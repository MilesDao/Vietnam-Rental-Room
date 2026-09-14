"""Export the raw-HTML alonhadat corpus to a flat, human-browsable CSV.

Same shape and feature set as export_mogi_to_sample.py -- same 31 columns,
same keyword-based amenity flags and utility-price snippets (both now shared
via src/export/text_features.py rather than copy-pasted a second time), same
Hanoi-only filter, same "read raw gzip HTML straight off disk" approach
(bypassing the cleaned Parquet, exactly like the mogi version does).

One deliberate difference: **`contact_phone`/`contact_zalo` hold the salted
phone_hash, not a raw phone number.** export_mogi_to_sample.py's version of
this file writes the unmasked phone into those columns, which is a real
violation of this project's own PII rule (see CLAUDE.md's "batdongsan
(prototype, cut) and the 'sample' export" section, and docs/PLAN.md/CLAUDE.md
generally: "A raw phone number or poster identity must never reach a parsed
row or an exported file"). It isn't fixed here retroactively -- that file's
behavior wasn't part of this request -- but it is not repeated for a second
source. alonhadat_parser.parse_detail_page() already returns the hash, so
this exporter uses it directly instead of re-deriving the raw number from HTML
the way export_mogi_to_sample.py does with its own _PHONE_RE/_AGENT_HREF_RE.

Usage:
    python -m src.export.export_alonhadat_to_sample
"""
from __future__ import annotations

import csv
import gzip
import logging
import sqlite3
from pathlib import Path

from src.export.text_features import extract_amenity_features, extract_utility_prices, get_amenities_list
from src.parse.alonhadat_parser import parse_detail_page

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "html" / "alonhadat"
DB_PATH = REPO_ROOT / "data" / "alonhadat_seen_urls.db"
OUT_CSV = REPO_ROOT / "alonhadat_hanoi_extracted.csv"

COLUMNS = [
    "platform", "listing_id", "title", "district", "ward", "address",
    "price_vnd", "house_type", "area_m2", "electric_price", "water_price",
    "wifi_price", "other_utilities_price", "parking_fee", "air_conditioner",
    "water_heater", "refrigerator", "washing_machine", "elevator",
    "balcony_window", "fire_safety", "pet_allowed", "amenities_list",
    "latitude", "longitude", "contact_name", "contact_phone", "contact_zalo",
    "image_count", "image_urls", "listing_url",
]


def known_urls() -> dict[str, str]:
    """listing_id -> url, from the crawl's own record of what it fetched.

    Mirrors reparse_alonhadat.py's known_urls(): the raw filename only
    encodes the native id, not the title-slug URL the site actually serves
    detail pages at, so recover the real one when we have it.
    """
    if not DB_PATH.exists():
        return {}
    with sqlite3.connect(DB_PATH) as conn:
        return dict(conn.execute("SELECT listing_id, url FROM seen_urls").fetchall())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("export_alonhadat")

    urls = known_urls()
    html_files = sorted(RAW_DIR.rglob("*.html.gz"))
    log.info("Found %d HTML files to process.", len(html_files))

    processed = 0
    hanoi_count = 0

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()

        for filepath in html_files:
            listing_id = filepath.name.removesuffix(".html.gz")
            url = urls.get(
                listing_id,
                f"https://alonhadat.com.vn/-{listing_id.removeprefix('alonhadat_')}.html",
            )
            try:
                with gzip.open(filepath, "rt", encoding="utf-8") as gz:
                    html = gz.read()

                parsed = parse_detail_page(html, url)

                if parsed.get("province") != "Hà Nội":
                    continue
                hanoi_count += 1

                desc = parsed.get("description") or ""
                features = extract_amenity_features(desc)
                utils = extract_utility_prices(desc)
                amenities = get_amenities_list(features)

                row = {
                    "platform": "Alonhadat.vn",
                    "listing_id": parsed.get("listing_id", ""),
                    "title": parsed.get("title", ""),
                    "district": parsed.get("district", ""),
                    "ward": parsed.get("ward", ""),
                    "address": parsed.get("address_raw", ""),
                    "price_vnd": parsed.get("price_vnd_month", ""),
                    "house_type": parsed.get("room_type", "Nhà trọ"),
                    "area_m2": parsed.get("area_m2", ""),
                    "electric_price": utils["electric_price"],
                    "water_price": utils["water_price"],
                    "wifi_price": utils["wifi_price"],
                    "other_utilities_price": utils["other_utilities_price"],
                    "parking_fee": utils["parking_fee"],
                    "air_conditioner": features["air_conditioner"],
                    "water_heater": features["water_heater"],
                    "refrigerator": features["refrigerator"],
                    "washing_machine": features["washing_machine"],
                    "elevator": features["elevator"],
                    "balcony_window": features["balcony_window"],
                    "fire_safety": features["fire_safety"],
                    "pet_allowed": features["pet_allowed"],
                    "amenities_list": amenities,
                    "latitude": parsed.get("lat", ""),
                    "longitude": parsed.get("lon", ""),
                    "contact_name": parsed.get("poster_name", ""),
                    "contact_phone": parsed.get("phone_hash", ""),
                    "contact_zalo": parsed.get("phone_hash", ""),
                    "image_count": parsed.get("n_images", 0),
                    "image_urls": " | ".join(parsed.get("image_urls", [])),
                    "listing_url": url,
                }
                writer.writerow(row)
            except Exception as e:
                log.error("Error processing %s: %s", filepath, e)

            processed += 1
            if processed % 100 == 0:
                log.info("Processed %d / %d ...", processed, len(html_files))

    log.info("Done! Extracted %d Hanoi records to %s", hanoi_count, OUT_CSV.name)


if __name__ == "__main__":
    main()
