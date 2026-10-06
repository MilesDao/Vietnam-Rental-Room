"""Hanoi phòng trọ from Nhatot (ex-Chotot) via the public JSON API, newest first.

    python crawlers/chotot/recrawl.py data/interim/recrawl_2026-10/nhatot.csv

Only category 1050 (Phòng trọ), region 12000 (Hà Nội). The link is built from `list_id`
(the id in nhatot.com/thue-phong-tro/<list_id>); detail HTML is never fetched (it answers scripts with 403).
Contact names/phones are not requested or stored.
"""
import json
import random
import sys
import time
from datetime import datetime, timezone

import pandas as pd
import requests

URL = "https://gateway.chotot.com/v1/public/ad-listing"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
LIMIT = 20


def fetch_all():
    ads, seen, offset = [], set(), 0
    while True:
        r = requests.get(URL, params={"cg": 1050, "limit": LIMIT, "o": offset, "st": "u", "region_v2": 12000},
                         headers={"User-Agent": UA}, timeout=20)
        if r.status_code == 429:
            time.sleep(30)
            continue
        r.raise_for_status()
        page = r.json().get("ads", [])
        if not page:
            return ads
        for a in page:
            if a.get("list_id") not in seen:
                seen.add(a["list_id"])
                ads.append(a)
        offset += LIMIT
        time.sleep(random.uniform(1.5, 3.0))


def to_row(a):
    imgs = a.get("images") or ([a["image"]] if a.get("image") else [])
    ts = a.get("list_time")
    return {
        "platform": "ChoTot.com",
        "listing_id": f"chotot_{a['list_id']}",
        "title": a.get("subject", ""),
        "description": a.get("body", ""),
        "district": a.get("area_name", ""),
        "ward": a.get("ward_name", ""),
        "address": ", ".join(x for x in [a.get("street_number"), a.get("street_name"), a.get("ward_name"), a.get("area_name"), "Hà Nội"] if x),
        "price_vnd": a.get("price"),
        "area_m2": a.get("size"),
        "house_type": a.get("category_name", "Phòng trọ"),
        "latitude": a.get("latitude"),
        "longitude": a.get("longitude"),
        "image_count": len(imgs),
        "image_urls": json.dumps(imgs),
        "listing_url": f"https://www.nhatot.com/thue-phong-tro/{a['list_id']}",
        "posted_at_raw": datetime.fromtimestamp(ts / 1000, timezone.utc).isoformat() if ts else "",
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "region_name": a.get("region_name", ""),
    }


if __name__ == "__main__":
    rows = [to_row(a) for a in fetch_all()]
    df = pd.DataFrame(rows)
    df = df[df.region_name == "Hà Nội"].drop(columns="region_name")   # Hanoi only, belt and braces
    df.to_csv(sys.argv[1], index=False, encoding="utf-8")
    print(f"{len(df)} Hanoi rooms -> {sys.argv[1]}")
