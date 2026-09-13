#!/usr/bin/env python3
"""
Crawler for rental rooms on yourhome.top
Extracts rental room listings from Next.js RSC state and saves to JSON and CSV formats.
"""

import argparse
import csv
import json
import os
import re
import urllib.request
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple


def fetch_page_content(url: str) -> str:
    """Fetch raw HTML content from the given URL."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def extract_balanced_json(text: str, key: str) -> Optional[List[Dict[str, Any]]]:
    """Extract a balanced JSON array keyed by `key` from RSC text."""
    pattern = f'"{key}":'
    idx = text.find(pattern)
    if idx == -1:
        return None

    arr_start = text.find("[", idx)
    if arr_start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for i in range(arr_start, len(text)):
        char = text[i]
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if not in_string:
            if char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    return json.loads(text[arr_start : i + 1])
    return None


def crawl_rooms(city: str = "ha-noi") -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """
    Crawls all rental rooms for the specified city.
    Returns (rooms, user_map, districts).
    """
    url = f"https://yourhome.top/?city={city}"
    print(f"Fetching data from {url}...")
    html = fetch_page_content(url)

    # Next.js App Router chunks are pushed via self.__next_f.push([1, "..."])
    raw_pushes = re.findall(r'self\.__next_f\.push\(\[1,\s*(".*?")\]\)', html, re.DOTALL)
    full_stream = "".join(json.loads(p) for p in raw_pushes)

    rooms = extract_balanced_json(full_stream, "initialRooms") or []
    users = extract_balanced_json(full_stream, "initialUsers") or []
    districts = extract_balanced_json(full_stream, "initialDistricts") or []

    user_map = {u.get("userId"): u.get("name") for u in users if u.get("userId")}

    # Match frontend logic: enrich contact name using user map if available
    for room in rooms:
        contact = room.get("contact") or {}
        user_id = room.get("userId", "")
        if user_id in user_map and user_map[user_id]:
            contact["name"] = user_map[user_id]
        room["contact"] = contact

    return rooms, user_map, districts


def save_to_json(rooms: List[Dict[str, Any]], output_path: str) -> None:
    """Save raw list of room dictionaries to formatted JSON."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(rooms, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(rooms)} rooms to JSON: {output_path}")


def save_to_csv(rooms: List[Dict[str, Any]], output_path: str) -> None:
    """Flatten and save room data into a tabular CSV file."""
    headers = [
        "id",
        "title",
        "price_vnd",
        "area_m2",
        "room_type",
        "district",
        "city",
        "location",
        "latitude",
        "longitude",
        "contact_name",
        "contact_phone",
        "contact_zalo",
        "alternative_phone",
        "amenities",
        "utility_costs",
        "restrictions",
        "is_available",
        "posted_date",
        "expires_at",
        "image_count",
        "image_urls",
        "description",
    ]

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()

        for room in rooms:
            contact = room.get("contact") or {}
            images = room.get("images") or []
            amenities = room.get("amenities") or []
            utility_costs = room.get("utilityCosts") or []
            restrictions = room.get("restrictions") or []

            row = {
                "id": room.get("id", ""),
                "title": room.get("title", "").strip(),
                "price_vnd": room.get("price", ""),
                "area_m2": room.get("area", ""),
                "room_type": room.get("roomType", ""),
                "district": room.get("district", ""),
                "city": room.get("city", ""),
                "location": room.get("location", ""),
                "latitude": room.get("lat", ""),
                "longitude": room.get("lng", ""),
                "contact_name": contact.get("name", "").strip(),
                "contact_phone": contact.get("phone", "").strip(),
                "contact_zalo": contact.get("zalo", "").strip(),
                "alternative_phone": contact.get("contactPhone", "").strip(),
                "amenities": "; ".join(amenities),
                "utility_costs": "; ".join(utility_costs),
                "restrictions": "; ".join(restrictions),
                "is_available": room.get("available", True),
                "posted_date": room.get("postedDate", ""),
                "expires_at": room.get("expiresAt", ""),
                "image_count": len(images),
                "image_urls": " | ".join(images),
                "description": room.get("description", "").strip(),
            }
            writer.writerow(row)

    print(f"Saved {len(rooms)} rooms to CSV: {output_path}")


def print_summary(rooms: List[Dict[str, Any]]) -> None:
    """Print quick stats about the crawled rooms."""
    if not rooms:
        print("No rooms found.")
        return

    prices = [r["price"] for r in rooms if isinstance(r.get("price"), (int, float))]
    areas = [r["area"] for r in rooms if isinstance(r.get("area"), (int, float))]

    districts = Counter(r.get("district", "Unknown") for r in rooms)
    room_types = Counter(r.get("roomType", "Unknown") for r in rooms)

    print("\n" + "=" * 50)
    print(f"CRAWL SUMMARY: Total {len(rooms)} rooms")
    print("=" * 50)
    if prices:
        print(f"Price: min {min(prices):,} VND | max {max(prices):,} VND | avg {int(sum(prices)/len(prices)):,} VND")
    if areas:
        print(f"Area: min {min(areas)} m² | max {max(areas)} m² | avg {sum(areas)/len(areas):.1f} m²")
    print("\nBreakdown by District:")
    for d, c in districts.most_common():
        print(f"  - {d}: {c} rooms")
    print("\nBreakdown by Room Type:")
    for t, c in room_types.most_common():
        print(f"  - {t}: {c} rooms")
    print("=" * 50)


def main() -> None:
    default_output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
    parser = argparse.ArgumentParser(description="Crawl rental rooms from yourhome.top")
    parser.add_argument("--city", default="ha-noi", help="City slug (default: ha-noi)")
    parser.add_argument("--output-dir", default=default_output_dir, help="Output directory for JSON and CSV (default: data/)")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    rooms, _, _ = crawl_rooms(city=args.city)

    json_file = os.path.join(args.output_dir, f"rooms_{args.city}.json")
    csv_file = os.path.join(args.output_dir, f"rooms_{args.city}.csv")

    save_to_json(rooms, json_file)
    save_to_csv(rooms, csv_file)
    print_summary(rooms)


if __name__ == "__main__":
    main()
