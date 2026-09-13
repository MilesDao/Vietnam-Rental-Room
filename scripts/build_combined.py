"""Merge per-group crawl outputs into one geocoded dataset.

Reads each group's ``data/<slug>/posts.jsonl`` (produced by the crawler),
adds a ``group_name`` column, geocodes each post to a Hà Nội district centroid
(``src.geocode``), de-duplicates *within* each group, and writes:

    data/posts_combined.csv
    data/posts_combined.jsonl

Run after crawling::

    python -m scripts.build_combined
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src import geocode
from src.exporter import CSV_COLUMNS
from src.utils import post_identity_key

# slug -> human-readable group name (edit to match the groups you crawled)
GROUPS = {
    "1164344644748784": "Tìm Phòng Trọ - Nhà Trọ Cho Sinh Viên Tại Hà Nội",
    "nhatrohngiare": "Phòng Trọ Hà Nội Giá Rẻ",
    "6603021829726413": "CHO THUÊ NHÀ VÀ PHÒNG TRỌ HÀ NỘI",
    "386158839291937": "Cho Thuê Phòng Trọ - Nhà Trọ - Tìm Người Ở Ghép Hà Nội",
}

GEO_COLS = ["district", "ward", "latitude", "longitude", "geo_precision"]
OUT_COLS = ["group_name"] + CSV_COLUMNS + GEO_COLS


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> None:
    seen: set[tuple[str, str]] = set()
    combined: list[dict] = []
    for slug, name in GROUPS.items():
        for r in _load(Path("data") / slug / "posts.jsonl"):
            r["group_name"] = name
            r.update(geocode.geocode_text(r.get("text")))
            key = (name, post_identity_key(r))  # dedupe within a group
            if key in seen:
                continue
            seen.add(key)
            combined.append(r)

    Path("data").mkdir(exist_ok=True)
    with open("data/posts_combined.jsonl", "w", encoding="utf-8") as f:
        for r in combined:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open("data/posts_combined.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLS, extrasaction="ignore")
        w.writeheader()
        for r in combined:
            row = {c: r.get(c) for c in OUT_COLS}
            row["image_urls"] = json.dumps(r.get("image_urls") or [], ensure_ascii=False)
            row["video_urls"] = json.dumps(r.get("video_urls") or [], ensure_ascii=False)
            w.writerow(row)

    print(f"combined {len(combined)} posts -> data/posts_combined.csv / .jsonl")


if __name__ == "__main__":
    main()
