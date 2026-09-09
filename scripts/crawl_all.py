"""
scripts/crawl_all.py - One-click Batch Crawler for Phongtro123 & Alonhadat

Crawls:
1. Phongtro123 (Hà Nội, TP.HCM)
2. Alonhadat (Hà Nội, TP.HCM)

Exports both JSON and CSV files to workspace root and data/interim/.
"""

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.crawl.run import run_crawler

TARGETS = [
    ("phongtro123", "hanoi"),
    ("phongtro123", "hcm"),
    ("alonhadat", "hanoi"),
    ("alonhadat", "hcm"),
]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="One-click crawler for Phongtro123 and Alonhadat (Hanoi & HCM)")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Number of pages to crawl per city/site (0 = ALL pages until end)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("🚀 STARTING AUTOMATED BATCH CRAWLER")
    print(f"Sites: phongtro123, alonhadat | Cities: Hanoi, HCM")
    print(f"Max pages per target: {'ALL' if args.max_pages == 0 else args.max_pages}")
    print("=" * 60)

    for idx, (site, city) in enumerate(TARGETS, 1):
        print(f"\n[{idx}/{len(TARGETS)}] >>> CRAWLING {site.upper()} ({city.upper()}) <<<")
        try:
            run_crawler(site=site, city=city, max_pages=args.max_pages)
        except Exception as e:
            print(f"❌ Error crawling {site} ({city}): {e}")

    print("\n" + "=" * 60)
    print("🎉 ALL BATCH CRAWLS COMPLETED!")
    print("Check CSV and JSON files exported at workspace root and data/interim/")
    print("=" * 60)
