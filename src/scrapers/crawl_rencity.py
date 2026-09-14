#!/usr/bin/env python3
"""
Crawler for Hanoi rental listings on Rencity (rencity.vn)
Fetches data from the public REST API: https://api1.renapp.vn/api/user/community/mo_posts
"""

import argparse
import csv
import json
import os
import time
import urllib.request
from collections import Counter
from typing import Any, Dict, List, Tuple

BASE_API = "https://api1.renapp.vn/api"


def fetch_posts_page(province_id: int = 1, page: int = 1, limit: int = 100) -> Dict[str, Any]:
    url = f"{BASE_API}/user/community/mo_posts?province_id={province_id}&page={page}&limit={limit}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return res.get("data", {})


def crawl_all_rencity_hanoi() -> List[Dict[str, Any]]:
    print("Starting crawl for Rencity Hanoi listings (province_id=1)...")
    first_page = fetch_posts_page(province_id=1, page=1, limit=100)
    total = first_page.get("total", 0)
    last_page = first_page.get("last_page", 1)
    all_items = list(first_page.get("data", []))

    print(f"Total listings reported: {total} across {last_page} pages.")
    print(f"Page 1/{last_page} fetched ({len(all_items)} items).")

    for p in range(2, last_page + 1):
        try:
            p_data = fetch_posts_page(province_id=1, page=p, limit=100)
            items = p_data.get("data", [])
            all_items.extend(items)
            print(f"Page {p}/{last_page} fetched ({len(items)} items). Total so far: {len(all_items)}")
            time.sleep(0.3)
        except Exception as e:
            print(f"Error on page {p}: {e}")

    return all_items


def save_to_json(items: List[Dict[str, Any]], filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(items)} listings to JSON: {filepath}")


def save_to_csv(items: List[Dict[str, Any]], filepath: str) -> None:
    headers = [
        "id",
        "title",
        "min_money_vnd",
        "max_money_vnd",
        "sale_money_vnd",
        "area_m2",
        "available_rooms",
        "province_name",
        "wards_name",
        "address_detail",
        "tower_id",
        "tower_name",
        "latitude",
        "longitude",
        "total_view",
        "image_count",
        "image_urls",
        "created_at",
        "updated_at",
        "post_url",
    ]

    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()

        for item in items:
            images = item.get("images") or []
            post_id = item.get("id", "")
            row = {
                "id": post_id,
                "title": (item.get("title") or "").strip(),
                "min_money_vnd": item.get("min_money") or "",
                "max_money_vnd": item.get("max_money") or "",
                "sale_money_vnd": item.get("sale_money") or "",
                "area_m2": item.get("area") or "",
                "available_rooms": item.get("available_rooms") or "",
                "province_name": item.get("province_name") or "",
                "wards_name": item.get("wards_name") or "",
                "address_detail": (item.get("address_detail") or "").strip(),
                "tower_id": item.get("tower_id") or "",
                "tower_name": item.get("tower_name") or "",
                "latitude": item.get("lat") or "",
                "longitude": item.get("lng") or "",
                "total_view": item.get("total_view") or "",
                "image_count": len(images),
                "image_urls": " | ".join(images),
                "created_at": item.get("created_at") or "",
                "updated_at": item.get("updated_at") or "",
                "post_url": f"https://rencity.vn/search?post_id={post_id}",
            }
            writer.writerow(row)

    print(f"Saved {len(items)} listings to CSV: {filepath}")


def print_summary(items: List[Dict[str, Any]]) -> None:
    if not items:
        print("No items to summarize.")
        return

    min_prices = [i["min_money"] for i in items if i.get("min_money") and i["min_money"] > 0]
    wards = Counter((i.get("wards_name") or "Chưa rõ") for i in items)

    print("\n" + "=" * 50)
    print(f"RENCITY HANOI CRAWL SUMMARY: Total {len(items)} listings")
    print("=" * 50)
    if min_prices:
        print(f"Price (min): lowest {min(min_prices):,} VND | highest {max(min_prices):,} VND | avg {int(sum(min_prices)/len(min_prices)):,} VND")
    print(f"Top 10 Wards / Areas:")
    for w, c in wards.most_common(10):
        print(f"  - {w}: {c} listings")
    print("=" * 50)


def main() -> None:
    default_output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
    parser = argparse.ArgumentParser(description="Crawl rental listings from Rencity")
    parser.add_argument("--output-dir", default=default_output_dir, help="Output directory (default: data/)")
    args = parser.parse_args()

    items = crawl_all_rencity_hanoi()
    json_path = os.path.join(args.output_dir, "rooms_rencity_hanoi.json")
    csv_path = os.path.join(args.output_dir, "rooms_rencity_hanoi.csv")

    save_to_json(items, json_path)
    save_to_csv(items, csv_path)
    print_summary(items)


if __name__ == "__main__":
    main()
