"""
src/parse/export.py - Export Parsed Listings to a Single CSV and Single JSON per Website

Ensures:
- Exactly 1 CSV and 1 JSON file per website (e.g. raw_phongtro123.csv, raw_phongtro123.json)
- Overwrites and merges with existing records by listing_id (preventing duplicate files/rows)
- UTF-8 BOM for Microsoft Excel compatibility
- Formatted JSON array
"""

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def save_site_dataset(
    records: List[Dict[str, Any]],
    output_dir: Path,
    site: str,
) -> Dict[str, Path]:
    """
    Save or merge records into a single raw_{site}.json and raw_{site}.csv in output_dir.
    Overwrites the files cleanly without creating extra date-stamped or city-specific files.

    Args:
        records: New parsed listing dictionaries
        output_dir: Target directory (e.g. workspace root or data/interim/)
        site: Site identifier ('phongtro123', 'alonhadat')

    Returns:
        Dict with 'json' and 'csv' paths
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"raw_{site}.json"
    csv_path = output_dir / f"raw_{site}.csv"

    # 1. Load existing records if file already exists to merge/upsert by listing_id
    existing_records: Dict[str, Dict[str, Any]] = {}
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    for item in loaded:
                        lid = item.get("listing_id")
                        if lid:
                            existing_records[lid] = item
        except Exception as e:
            logger.warning(f"Could not read existing {json_path}: {e}")

    from src.parse.normalizer import enrich_record

    # Upsert new records into existing dictionary
    import datetime
    for rec in records:
        lid = rec.get("listing_id")
        if lid:
            if "url" in rec and isinstance(rec["url"], str):
                rec["url"] = re.sub(r"(\.html)+$", ".html", rec["url"])
            if not rec.get("crawled_at") and lid in existing_records and existing_records[lid].get("crawled_at"):
                rec["crawled_at"] = existing_records[lid]["crawled_at"]
            elif not rec.get("crawled_at"):
                rec["crawled_at"] = datetime.datetime.now().isoformat()
            
            # Clean up old field names
            if "price_vnd_month" in rec and "price_vnd" not in rec:
                rec["price_vnd"] = rec.pop("price_vnd_month")
            elif "price" in rec and "price_vnd" not in rec:
                rec["price_vnd"] = rec.pop("price")
            rec.pop("price_is_negotiable", None)
            rec.pop("price_vnd_month", None)
            rec.pop("price", None)
            rec.pop("phone_hash", None)

            existing_records[lid] = enrich_record(rec)

    from src.parse.filter import is_valid_rental_room, MAX_RENTAL_PRICE_VND

    all_records = []
    for r in existing_records.values():
        if "url" in r and isinstance(r["url"], str):
            r["url"] = re.sub(r"(\.html)+$", ".html", r["url"])
        if not r.get("crawled_at"):
            r["crawled_at"] = datetime.datetime.now().isoformat()
        if "price_vnd_month" in r and "price_vnd" not in r:
            r["price_vnd"] = r.pop("price_vnd_month")
        elif "price" in r and "price_vnd" not in r:
            r["price_vnd"] = r.pop("price")
        r.pop("price_is_negotiable", None)
        r.pop("price_vnd_month", None)
        r.pop("price", None)
        r.pop("phone_hash", None)
        if "price_vnd" in r and isinstance(r["price_vnd"], (int, float)):
            if abs(r["price_vnd"] - round(r["price_vnd"])) < 1e-4:
                r["price_vnd"] = round(r["price_vnd"])
        
        # Validate rental room property (all prices allowed when MAX_RENTAL_PRICE_VND is None)
        is_val, reason = is_valid_rental_room(r, max_price=MAX_RENTAL_PRICE_VND, allow_negotiable=True)
        if is_val:
            all_records.append(r)
        else:
            logger.debug(f"Excluded invalid listing {r.get('listing_id')}: {reason}")

    # 2. Overwrite JSON file (Formatted Array)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)
    logger.info(f"✅ Overwritten JSON: {json_path} (Total {len(all_records)} records)")

    # 3. Canonical field order for CSV (33 Standardized Columns)
    CANONICAL_COLUMNS = [
        "listing_id", "source", "url", "title", "description",
        "price_vnd", "area_m2", "address_raw",
        "city", "district", "ward", "house_type",
        "latitude", "longitude",
        "electric_price", "water_price", "wifi_price", "other_utilities_price", "parking_fee",
        "air_conditioner", "water_heater", "refrigerator", "washing_machine", "elevator", "balcony_window", "fire_safety", "pet_allowed",
        "room_type", "posted_at_raw", "phone_number", "image_urls", "n_images", "crawled_at"
    ]

    all_keys = [k for k in CANONICAL_COLUMNS]
    for r in all_records:
        for k in r.keys():
            if k not in all_keys:
                all_keys.append(k)

    # 4. Overwrite CSV file (UTF-8 BOM for Excel)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for r in all_records:
            row = {}
            for k in all_keys:
                val = r.get(k)
                if isinstance(val, (list, dict)):
                    row[k] = json.dumps(val, ensure_ascii=False)
                elif val is None:
                    row[k] = ""
                else:
                    row[k] = val
            writer.writerow(row)
    logger.info(f"✅ Overwritten CSV: {csv_path} (Total {len(all_records)} records)")

    return {"json": json_path, "csv": csv_path}


# Backward compatibility alias
def export_records(
    records: List[Dict[str, Any]],
    output_base_path: Path,
    file_prefix: str,
) -> Dict[str, Path]:
    site = "phongtro123" if "phongtro123" in file_prefix else "alonhadat"
    return save_site_dataset(records, output_base_path, site)
