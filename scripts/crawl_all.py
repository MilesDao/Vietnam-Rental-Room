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
    ("phongtro123", "hanoi_ccmn"),
    ("phongtro123", "hanoi_oghep"),
    ("phongtro123", "hanoi_dichvu"),
    ("phongtro123", "hanoi_nhanguyencan"),
    ("phongtro123", "hanoi"),
    ("phongtro123", "hcm"),
    ("alonhadat", "hanoi"),
    ("alonhadat", "hcm"),
]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="One-click crawler for Phongtro123 and Alonhadat")
    parser.add_argument(
        "--site",
        type=str,
        default="all",
        choices=["all", "phongtro123", "alonhadat"],
        help="Site to crawl ('phongtro123', 'alonhadat', or 'all' for both)",
    )
    parser.add_argument(
        "--city",
        type=str,
        default="all",
        choices=["all", "hanoi", "hcm"],
        help="City to crawl ('hanoi', 'hcm', or 'all' for both)",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="Start page for crawling pagination (default: 1)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Number of pages to crawl per city/site (0 = ALL pages until end)",
    )
    parser.add_argument(
        "--include-expired",
        action="store_true",
        default=False,
        help="Include expired / historical listings in crawl",
    )
    parser.add_argument(
        "--allow-negotiable",
        action="store_true",
        default=False,
        help="Allow listings with negotiable / unspecified prices",
    )
    args = parser.parse_args()

    targets = TARGETS
    if args.site != "all":
        targets = [t for t in targets if t[0] == args.site]
    if args.city != "all":
        targets = [t for t in targets if args.city in t[1]]

    print("=" * 60)
    print("🚀 STARTING AUTOMATED BATCH CRAWLER")
    print(f"Sites: {args.site.upper()} | City: {args.city.upper()}")
    print(f"Start page: {args.start_page} | Max pages: {'ALL' if args.max_pages == 0 else args.max_pages}")
    print(f"Include Expired: {args.include_expired} | Allow Negotiable: {args.allow_negotiable}")
    print("=" * 60)

    for idx, (site, city) in enumerate(targets, 1):
        print(f"\n[{idx}/{len(targets)}] >>> CRAWLING {site.upper()} ({city.upper()}) <<<")
        try:
            run_crawler(
                site=site,
                city=city,
                start_page=args.start_page,
                max_pages=args.max_pages,
                include_expired=args.include_expired,
                allow_negotiable=args.allow_negotiable,
            )
        except Exception as e:
            print(f"❌ Error crawling {site} ({city}): {e}")

    print("\n" + "=" * 60)
    print("🎉 ALL BATCH CRAWLS COMPLETED!")
    print("Check CSV and JSON files exported at workspace root and data/interim/")
    print("=" * 60)
