#!/usr/bin/env python3
"""
Crawler for Hanoi rental buildings/rooms on PhongTot (phongtot.com)
Extracts building listings, address, area, price, building amenities, and images from SSR HTML.
"""

import argparse
import csv
import json
import os
import re
import time
import urllib.request
from collections import Counter
from html import unescape
from typing import Any, Dict, List, Optional

BASE_URL = "https://phongtot.com/cho-thue-phong-tro-hn"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_building_card(chunk: str) -> Optional[Dict[str, Any]]:
    # Extract building link and id
    link_m = re.search(r'href="(/cho-thue-phong-tro-hn/([^/]+)/([^"]+-tn(\d+)))"', chunk)
    if not link_m:
        return None

    rel_link, district, slug, tn_id = link_m.groups()

    # Images
    images = list(dict.fromkeys(re.findall(r'src="(https://cdn\.phongtot\.com/store/[^"]+)"', chunk)))

    # Parse text lines
    clean = re.sub(r'<[^>]+>', '\n', chunk)
    lines = [unescape(l.strip()) for l in clean.splitlines() if l.strip()]

    title = ""
    address = ""
    area = ""
    min_price_vnd = ""
    status_text = ""
    amenities = []

    # Title is usually the first line with Vietnamese text or building name
    for i, line in enumerate(lines):
        if line.startswith("RenHouse") or line.startswith("TV Home") or line.startswith("Sunshine") or "Phòng" in line or "Tòa" in line or "Nhà" in line or len(line) > 10:
            if not title and not line.startswith("p-3") and not line.startswith("+") and "Tiện ích" not in line:
                title = line
                if i + 1 < len(lines):
                    address = lines[i + 1]
                break

    # Look for area (e.g. 25 m2 or 28 - 32 m2)
    area_m = re.search(r'(\d+\s*-\s*\d+|\d+)\s*m2', chunk)
    if area_m:
        area = area_m.group(0).strip()

    # Look for price "Chỉ từ X.XXX.XXXđ"
    price_m = re.search(r'Chỉ từ\s*([0-9\.]+)\s*đ', unescape(chunk))
    if price_m:
        min_price_vnd = price_m.group(1).replace(".", "").strip()

    # Look for room vacancy text (e.g. "Chỉ còn X phòng trống!")
    status_m = re.search(r'(Chỉ còn\s*\d+\s*phòng trống!?)', unescape(chunk))
    if status_m:
        status_text = status_m.group(1).strip()

    # Common building amenities
    common_amenities = [
        "Ô tô đỗ cửa", "Camera an ninh", "Khóa cổng thông minh", "Bình chữa cháy",
        "Thang máy", "Máy giặt chung", "Bảo vệ 24/7", "Giờ giấc tự do", "Khu để xe"
    ]
    u_chunk = unescape(chunk)
    for am in common_amenities:
        if am in u_chunk and am not in amenities:
            amenities.append(am)

    return {
        "id": tn_id,
        "title": title or slug,
        "district": district.replace("quan-", "").replace("huyen-", "").title(),
        "address": address,
        "area": area,
        "min_price_vnd": min_price_vnd,
        "status": status_text or "Đang cho thuê",
        "amenities": amenities,
        "image_count": len(images),
        "images": images,
        "url": f"https://phongtot.com{rel_link}",
    }


def crawl_phongtot(max_pages: int = 10) -> List[Dict[str, Any]]:
    print(f"Starting PhongTot Hanoi crawl (up to {max_pages} pages)...")
    all_buildings = []
    seen_ids = set()

    for page in range(1, max_pages + 1):
        url = f"{BASE_URL}?st={page}"
        html = None
        for attempt in range(3):
            try:
                html = fetch_html(url)
                break
            except Exception as e:
                if attempt == 2:
                    print(f"Failed page {page} after 3 attempts: {e}")
                else:
                    time.sleep(1.0)

        if not html:
            continue

        card_chunks = re.split(r'<div class="flex flex-col w-\[280px\]', html)
        page_items = []
        for chunk in card_chunks[1:]:
            item = parse_building_card(chunk)
            if item and item["id"] not in seen_ids:
                seen_ids.add(item["id"])
                page_items.append(item)
                all_buildings.append(item)

        print(f"Page {page}/{max_pages}: +{len(page_items)} buildings (Total: {len(all_buildings)})")
        if len(page_items) == 0 and page > 10:
            print(f"No items found at page {page}. Stopping.")
            break
        time.sleep(0.3)

    return all_buildings


def save_to_json(items: List[Dict[str, Any]], filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(items)} buildings to JSON: {filepath}")


def save_to_csv(items: List[Dict[str, Any]], filepath: str) -> None:
    headers = [
        "id",
        "title",
        "district",
        "address",
        "area",
        "min_price_vnd",
        "status",
        "amenities",
        "image_count",
        "image_urls",
        "url",
    ]

    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()

        for item in items:
            row = {
                "id": item.get("id", ""),
                "title": item.get("title", ""),
                "district": item.get("district", ""),
                "address": item.get("address", ""),
                "area": item.get("area", ""),
                "min_price_vnd": item.get("min_price_vnd", ""),
                "status": item.get("status", ""),
                "amenities": "; ".join(item.get("amenities", [])),
                "image_count": item.get("image_count", 0),
                "image_urls": " | ".join(item.get("images", [])),
                "url": item.get("url", ""),
            }
            writer.writerow(row)

    print(f"Saved {len(items)} buildings to CSV: {filepath}")


def print_summary(items: List[Dict[str, Any]]) -> None:
    if not items:
        print("No items to summarize.")
        return

    prices = [int(i["min_price_vnd"]) for i in items if i.get("min_price_vnd") and i["min_price_vnd"].isdigit()]
    districts = Counter(i.get("district", "Unknown") for i in items)

    print("\n" + "=" * 50)
    print(f"PHONGTOT HANOI CRAWL SUMMARY: Total {len(items)} buildings")
    print("=" * 50)
    if prices:
        print(f"Price (min): lowest {min(prices):,} VND | highest {max(prices):,} VND | avg {int(sum(prices)/len(prices)):,} VND")
    print("Breakdown by District:")
    for d, c in districts.most_common():
        print(f"  - {d}: {c} buildings")
    print("=" * 50)


def main() -> None:
    default_output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
    parser = argparse.ArgumentParser(description="Crawl Hanoi rentals from PhongTot")
    parser.add_argument("--pages", type=int, default=15, help="Number of pages to crawl (default: 15)")
    parser.add_argument("--output-dir", default=default_output_dir, help="Output directory (default: data/)")
    args = parser.parse_args()

    items = crawl_phongtot(max_pages=args.pages)
    json_path = os.path.join(args.output_dir, "rooms_phongtot_hanoi.json")
    csv_path = os.path.join(args.output_dir, "rooms_phongtot_hanoi.csv")

    save_to_json(items, json_path)
    save_to_csv(items, csv_path)
    print_summary(items)


if __name__ == "__main__":
    main()
