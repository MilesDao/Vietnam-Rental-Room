#!/usr/bin/env python3
"""
merge_crawl_results.py

Merges rental housing datasets crawled from 8 platforms across Hanoi:
  1. hanoi_listings_clean.csv (Mogi.vn, Alonhadat.vn, PhongTot.com, Rencity.vn, YourHome.top)
  2. chotot_hanoi_cleaned.csv (ChoTot.com)
  3. phongtro123_cleaned.csv (Phongtro123.com)
  4. facebook_rentals_parsed.csv (Facebook Rental Groups)

Outputs:
  - merged_hanoi_rentals.csv (Comprehensive unified dataset)
"""

import csv
import os
import re
from collections import Counter
from typing import Any, Dict, List

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

PREFIX_REGEX = re.compile(r"^(quận|huyện|thị xã)\s+", re.IGNORECASE)

CANONICAL_COLUMNS = [
    "listing_id",
    "platform",
    "source_file",
    "title",
    "description",
    "city",
    "district",
    "district_raw",
    "ward",
    "address",
    "latitude",
    "longitude",
    "price_vnd",
    "area_m2",
    "house_type",
    "electric_price",
    "water_price",
    "wifi_price",
    "other_utilities_price",
    "parking_fee",
    "air_conditioner",
    "water_heater",
    "refrigerator",
    "washing_machine",
    "elevator",
    "balcony_window",
    "fire_safety",
    "pet_allowed",
    "amenities_list",
    "contact_name",
    "contact_phone",
    "contact_zalo",
    "image_count",
    "image_urls",
    "listing_url",
    "posted_at_raw",
    "crawled_at",
]

def norm_bool(val: Any) -> str:
    if val is None:
        return "False"
    s = str(val).strip().lower()
    if s in ("true", "1", "t", "yes", "có"):
        return "True"
    return "False"

def clean_str(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if s.lower() in ("nan", "none", "null"):
        return ""
    return s

def clean_district(raw_district: str) -> str:
    s = clean_str(raw_district)
    if not s:
        return ""
    s_norm = PREFIX_REGEX.sub("", s).strip()
    return s_norm

def build_amenities_str(row: Dict[str, str]) -> str:
    flags = [
        ("Điều hòa", row.get("air_conditioner")),
        ("Nóng lạnh", row.get("water_heater")),
        ("Tủ lạnh", row.get("refrigerator")),
        ("Máy giặt", row.get("washing_machine")),
        ("Thang máy", row.get("elevator")),
        ("Ban công/Cửa sổ", row.get("balcony_window")),
        ("PCCC", row.get("fire_safety")),
        ("Cho nuôi thú cưng", row.get("pet_allowed")),
    ]
    present = [label for label, val in flags if norm_bool(val) == "True"]
    return "; ".join(present)

def process_hanoi_clean(filepath: str) -> List[Dict[str, str]]:
    results = []
    with open(filepath, mode="r", encoding="utf-8", errors="replace") as fp:
        reader = csv.DictReader(fp)
        reader.fieldnames = [c.lstrip("\ufeff") for c in reader.fieldnames]
        for row in reader:
            lid = clean_str(row.get("listing_id"))
            if not lid:
                continue
            plat = clean_str(row.get("platform")) or "Unknown"
            raw_dist = clean_str(row.get("district_raw")) or clean_str(row.get("district"))
            dist = clean_district(row.get("district", "")) or clean_district(raw_dist)

            # price formatting
            price = clean_str(row.get("price_vnd"))
            if price:
                try:
                    f_p = float(price)
                    price = f"{int(f_p)}" if f_p.is_integer() else f"{f_p:.2f}"
                except ValueError:
                    pass

            item = {
                "listing_id": lid,
                "platform": plat,
                "source_file": clean_str(row.get("source_file")) or os.path.basename(filepath),
                "title": clean_str(row.get("title")),
                "description": "",
                "city": "Hà Nội",
                "district": dist,
                "district_raw": raw_dist,
                "ward": clean_str(row.get("ward")),
                "address": clean_str(row.get("address")),
                "latitude": clean_str(row.get("latitude")),
                "longitude": clean_str(row.get("longitude")),
                "price_vnd": price,
                "area_m2": clean_str(row.get("area_m2")),
                "house_type": clean_str(row.get("house_type")),
                "electric_price": clean_str(row.get("electric_price")),
                "water_price": clean_str(row.get("water_price")),
                "wifi_price": clean_str(row.get("wifi_price")),
                "other_utilities_price": clean_str(row.get("other_utilities_price")),
                "parking_fee": clean_str(row.get("parking_fee")),
                "air_conditioner": norm_bool(row.get("air_conditioner")),
                "water_heater": norm_bool(row.get("water_heater")),
                "refrigerator": norm_bool(row.get("refrigerator")),
                "washing_machine": norm_bool(row.get("washing_machine")),
                "elevator": norm_bool(row.get("elevator")),
                "balcony_window": norm_bool(row.get("balcony_window")),
                "fire_safety": norm_bool(row.get("fire_safety")),
                "pet_allowed": norm_bool(row.get("pet_allowed")),
                "amenities_list": clean_str(row.get("amenities_list")),
                "contact_name": clean_str(row.get("contact_name")),
                "contact_phone": clean_str(row.get("contact_phone")),
                "contact_zalo": clean_str(row.get("contact_zalo")),
                "image_count": clean_str(row.get("image_count")),
                "image_urls": clean_str(row.get("image_urls")),
                "listing_url": clean_str(row.get("listing_url")),
                "posted_at_raw": "",
                "crawled_at": "",
            }
            if not item["amenities_list"]:
                item["amenities_list"] = build_amenities_str(item)
            results.append(item)
    return results

def process_chotot(filepath: str) -> List[Dict[str, str]]:
    results = []
    with open(filepath, mode="r", encoding="utf-8", errors="replace") as fp:
        reader = csv.DictReader(fp)
        reader.fieldnames = [c.lstrip("\ufeff") for c in reader.fieldnames]
        for row in reader:
            lid = clean_str(row.get("listing_id"))
            if not lid:
                continue
            raw_dist = clean_str(row.get("district"))
            dist = clean_district(raw_dist)

            parking_val = norm_bool(row.get("parking"))
            parking_fee = "Có chỗ để xe" if parking_val == "True" else ""

            price = clean_str(row.get("price_vnd"))
            if price:
                try:
                    f_p = float(price)
                    price = f"{int(f_p)}" if f_p.is_integer() else f"{f_p:.2f}"
                except ValueError:
                    pass

            item = {
                "listing_id": f"chotot_{lid}" if not lid.startswith("chotot_") else lid,
                "platform": "ChoTot.com",
                "source_file": os.path.basename(filepath),
                "title": clean_str(row.get("title")),
                "description": clean_str(row.get("body")),
                "city": "Hà Nội",
                "district": dist,
                "district_raw": raw_dist,
                "ward": clean_str(row.get("ward")),
                "address": clean_str(row.get("address")),
                "latitude": clean_str(row.get("latitude")),
                "longitude": clean_str(row.get("longitude")),
                "price_vnd": price,
                "area_m2": clean_str(row.get("area_m2")),
                "house_type": clean_str(row.get("house_type")),
                "electric_price": clean_str(row.get("electric_price")),
                "water_price": clean_str(row.get("water_price")),
                "wifi_price": clean_str(row.get("wifi_price")),
                "other_utilities_price": clean_str(row.get("other_uti")),
                "parking_fee": parking_fee,
                "air_conditioner": norm_bool(row.get("air_condi")),
                "water_heater": norm_bool(row.get("water_he")),
                "refrigerator": norm_bool(row.get("refrigerat")),
                "washing_machine": norm_bool(row.get("washing")),
                "elevator": norm_bool(row.get("elevator")),
                "balcony_window": norm_bool(row.get("balcony")),
                "fire_safety": norm_bool(row.get("fire_safet")),
                "pet_allowed": norm_bool(row.get("pet_allow")),
                "amenities_list": clean_str(row.get("amenities")),
                "contact_name": clean_str(row.get("contact_name")),
                "contact_phone": clean_str(row.get("contact_phone")),
                "contact_zalo": clean_str(row.get("contact_zalo")),
                "image_count": clean_str(row.get("image_co")),
                "image_urls": clean_str(row.get("image_u")),
                "listing_url": clean_str(row.get("listing_ur")),
                "posted_at_raw": "",
                "crawled_at": "",
            }
            if not item["amenities_list"]:
                item["amenities_list"] = build_amenities_str(item)
            results.append(item)
    return results

def process_phongtro123(filepath: str) -> List[Dict[str, str]]:
    results = []
    with open(filepath, mode="r", encoding="utf-8", errors="replace") as fp:
        reader = csv.DictReader(fp)
        reader.fieldnames = [c.lstrip("\ufeff") for c in reader.fieldnames]
        for row in reader:
            lid = clean_str(row.get("listing_id"))
            if not lid:
                continue
            raw_city = clean_str(row.get("city")).lower()
            if "hồ chí minh" in raw_city or "ho chi minh" in raw_city:
                city = "Hồ Chí Minh"
            else:
                city = "Hà Nội"

            raw_dist = clean_str(row.get("district"))
            dist = clean_district(raw_dist)

            price = clean_str(row.get("price_vnd"))
            if price:
                try:
                    f_p = float(price)
                    price = f"{int(f_p)}" if f_p.is_integer() else f"{f_p:.2f}"
                except ValueError:
                    pass

            item = {
                "listing_id": lid,
                "platform": "Phongtro123.com",
                "source_file": os.path.basename(filepath),
                "title": clean_str(row.get("title")),
                "description": clean_str(row.get("description")),
                "city": city,
                "district": dist,
                "district_raw": raw_dist,
                "ward": clean_str(row.get("ward")),
                "address": clean_str(row.get("address_raw")),
                "latitude": clean_str(row.get("latitude")),
                "longitude": clean_str(row.get("longitude")),
                "price_vnd": price,
                "area_m2": clean_str(row.get("area_m2")),
                "house_type": clean_str(row.get("house_type")),
                "electric_price": clean_str(row.get("electric_price")),
                "water_price": clean_str(row.get("water_price")),
                "wifi_price": clean_str(row.get("wifi_price")),
                "other_utilities_price": clean_str(row.get("other_utilities_price")),
                "parking_fee": clean_str(row.get("parking_fee")),
                "air_conditioner": norm_bool(row.get("air_conditioner")),
                "water_heater": norm_bool(row.get("water_heater")),
                "refrigerator": norm_bool(row.get("refrigerator")),
                "washing_machine": norm_bool(row.get("washing_machine")),
                "elevator": norm_bool(row.get("elevator")),
                "balcony_window": norm_bool(row.get("balcony_window")),
                "fire_safety": norm_bool(row.get("fire_safety")),
                "pet_allowed": norm_bool(row.get("pet_allowed")),
                "amenities_list": "",
                "contact_name": "",
                "contact_phone": clean_str(row.get("phone_number")),
                "contact_zalo": "",
                "image_count": clean_str(row.get("n_images")),
                "image_urls": clean_str(row.get("image_urls")),
                "listing_url": clean_str(row.get("url")),
                "posted_at_raw": clean_str(row.get("posted_at_raw")),
                "crawled_at": clean_str(row.get("crawled_at")),
            }
            item["amenities_list"] = build_amenities_str(item)
            results.append(item)
    return results

def process_facebook(filepath: str) -> List[Dict[str, str]]:
    results = []
    districts_lookup = [
        "Cầu Giấy", "Ba Đình", "Đống Đa", "Hai Bà Trưng", "Hoàn Kiếm", "Tây Hồ",
        "Thanh Xuân", "Hoàng Mai", "Long Biên", "Nam Từ Liêm", "Bắc Từ Liêm",
        "Hà Đông", "Sơn Tây", "Ba Vì", "Chương Mỹ", "Đan Phượng", "Đông Anh",
        "Gia Lâm", "Hoài Đức", "Mê Linh", "Mỹ Đức", "Phú Xuyên", "Phúc Thọ",
        "Quốc Oai", "Sóc Sơn", "Thạch Thất", "Thanh Oai", "Thanh Trì", "Thường Tín", "Ứng Hòa"
    ]
    with open(filepath, mode="r", encoding="utf-8", errors="replace") as fp:
        reader = csv.DictReader(fp)
        reader.fieldnames = [c.lstrip("\ufeff") for c in reader.fieldnames]
        for row in reader:
            lid = clean_str(row.get("listing_id"))
            if not lid:
                continue
            raw_dist = clean_str(row.get("district"))
            dist = clean_district(raw_dist)
            if not dist:
                addr_text = (clean_str(row.get("geocoded_address")) + " " + clean_str(row.get("address_raw"))).lower()
                for d_cand in districts_lookup:
                    if d_cand.lower() in addr_text:
                        dist = d_cand
                        raw_dist = d_cand
                        break

            price = clean_str(row.get("price_vnd_month"))
            if price:
                try:
                    f_p = float(price)
                    price = f"{int(f_p)}" if f_p.is_integer() else f"{f_p:.2f}"
                except ValueError:
                    pass

            addr = clean_str(row.get("address_raw")) or clean_str(row.get("geocoded_address"))

            item = {
                "listing_id": lid,
                "platform": "Facebook",
                "source_file": os.path.basename(filepath),
                "title": clean_str(row.get("title")),
                "description": clean_str(row.get("description")),
                "city": "Hà Nội",
                "district": dist,
                "district_raw": raw_dist,
                "ward": clean_str(row.get("ward")),
                "address": addr,
                "latitude": clean_str(row.get("latitude")),
                "longitude": clean_str(row.get("longitude")),
                "price_vnd": price,
                "area_m2": clean_str(row.get("area_m2")),
                "house_type": clean_str(row.get("house_type")),
                "electric_price": clean_str(row.get("electric_price")),
                "water_price": clean_str(row.get("water_price")),
                "wifi_price": clean_str(row.get("wifi_price")),
                "other_utilities_price": clean_str(row.get("other_utilities_price")),
                "parking_fee": clean_str(row.get("parking_fee")),
                "air_conditioner": norm_bool(row.get("air_conditioner")),
                "water_heater": norm_bool(row.get("water_heater")),
                "refrigerator": norm_bool(row.get("refrigerator")),
                "washing_machine": norm_bool(row.get("washing_machine")),
                "elevator": norm_bool(row.get("elevator")),
                "balcony_window": norm_bool(row.get("balcony_window")),
                "fire_safety": norm_bool(row.get("fire_safety")),
                "pet_allowed": norm_bool(row.get("pet_allowed")),
                "amenities_list": "",
                "contact_name": "",
                "contact_phone": clean_str(row.get("phone_hash")),
                "contact_zalo": "",
                "image_count": clean_str(row.get("n_images")),
                "image_urls": clean_str(row.get("image_urls")),
                "listing_url": clean_str(row.get("url")),
                "posted_at_raw": clean_str(row.get("posted_at_raw")),
                "crawled_at": clean_str(row.get("crawled_at")),
            }
            item["amenities_list"] = build_amenities_str(item)
            results.append(item)
    return results

def main():
    print("Starting crawl results merge...")
    clean_csv = os.path.join(DATA_DIR, "hanoi_listings_clean.csv")
    chotot_csv = os.path.join(DATA_DIR, "chotot_hanoi_cleaned.csv")
    phongtro123_csv = os.path.join(DATA_DIR, "phongtro123_cleaned.csv")
    facebook_csv = os.path.join(DATA_DIR, "facebook_rentals_geocoded_offline_full.csv")
    if not os.path.exists(facebook_csv):
        facebook_csv = os.path.join(DATA_DIR, "facebook_rentals_parsed.csv")

    all_records: List[Dict[str, str]] = []
    seen_ids = set()

    # 1. Hanoi Clean (Mogi, Alonhadat, PhongTot, Rencity, YourHome)
    if os.path.exists(clean_csv):
        print(f"Loading {clean_csv}...")
        rec = process_hanoi_clean(clean_csv)
        for r in rec:
            if r["listing_id"] not in seen_ids:
                seen_ids.add(r["listing_id"])
                all_records.append(r)
        print(f"  Loaded {len(rec)} records (Total so far: {len(all_records)})")

    # 2. ChoTot
    if os.path.exists(chotot_csv):
        print(f"Loading {chotot_csv}...")
        rec = process_chotot(chotot_csv)
        added = 0
        for r in rec:
            if r["listing_id"] not in seen_ids:
                seen_ids.add(r["listing_id"])
                all_records.append(r)
                added += 1
        print(f"  Loaded {len(rec)} records, {added} new unique (Total so far: {len(all_records)})")

    # 3. Phongtro123
    if os.path.exists(phongtro123_csv):
        print(f"Loading {phongtro123_csv}...")
        rec = process_phongtro123(phongtro123_csv)
        added = 0
        for r in rec:
            if r["listing_id"] not in seen_ids:
                seen_ids.add(r["listing_id"])
                all_records.append(r)
                added += 1
        print(f"  Loaded {len(rec)} records, {added} new unique (Total so far: {len(all_records)})")

    # 4. Facebook
    if os.path.exists(facebook_csv):
        print(f"Loading {facebook_csv}...")
        rec = process_facebook(facebook_csv)
        added = 0
        for r in rec:
            if r["listing_id"] not in seen_ids:
                seen_ids.add(r["listing_id"])
                all_records.append(r)
                added += 1
        print(f"  Loaded {len(rec)} records, {added} new unique (Total so far: {len(all_records)})")

    # Save to merged_hanoi_rentals.csv
    out_csv = os.path.join(DATA_DIR, "merged_hanoi_rentals.csv")
    print(f"\nWriting {len(all_records)} merged listings to {out_csv}...")
    with open(out_csv, mode="w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=CANONICAL_COLUMNS)
        writer.writeheader()
        writer.writerows(all_records)

    print(f"Merge completed successfully! Output: {out_csv}")
    print("\n--- Platform Distribution ---")
    plat_counts = Counter(r["platform"] for r in all_records)
    for plat, count in plat_counts.most_common():
        print(f"  {plat}: {count:,} ({count/len(all_records)*100:.1f}%)")

    print("\n--- City Distribution ---")
    city_counts = Counter(r["city"] for r in all_records)
    for city, count in city_counts.most_common():
        print(f"  {city}: {count:,} ({count/len(all_records)*100:.1f}%)")

    print("\n--- Top Districts ---")
    dist_counts = Counter(r["district"] for r in all_records if r["district"])
    for dist, count in dist_counts.most_common(12):
        print(f"  {dist}: {count:,}")

if __name__ == "__main__":
    main()
