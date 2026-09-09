"""
src/crawl/run.py - Unified Crawler Runner & Exporter CLI

Supports:
  1. Phongtro123: Discovery + Detail HTML fetch + Parse
  2. Alonhadat: Discovery + Detail HTML fetch + Parse
  3. Chotot: Direct Public API crawl (cg=1050, cg=1010, cg=1020)
  
Output:
  - Compressed raw HTML in data/raw/html/
  - JSON Lines (.jsonl) in data/interim/
  - JSON Array (.json) in data/interim/ and root
  - Flat tabular CSV (.csv with UTF-8 BOM for Excel) in data/interim/ and root
"""

import argparse
import datetime
import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import List, Set
from bs4 import BeautifulSoup
import yaml

from src.crawl.fetcher import PoliteFetcher
from src.parse.phongtro123_parser import parse_phongtro123_detail
from src.parse.alonhadat_parser import parse_alonhadat_detail
from src.crawl.chotot_crawler import ChototCrawler
from src.parse.export import export_records

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("crawl_runner")

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize SQLite frontier database for tracking seen URLs."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_urls (
            url TEXT PRIMARY KEY,
            site TEXT NOT NULL,
            city TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'discovered',
            crawled_at TIMESTAMP,
            error TEXT
        )
        """
    )
    conn.commit()
    return conn


def extract_list_links_phongtro123(html: str, base_url: str) -> List[str]:
    """Extract detail listing URLs from a phongtro123 list page."""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    links: Set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if "-pr" in href and ".html" in href:
            if href.startswith("/"):
                href = base_url.rstrip("/") + href
            if href.startswith("http"):
                links.add(href)
    return sorted(list(links))


def extract_list_links_alonhadat(html: str, base_url: str) -> List[str]:
    """Extract detail listing URLs from an alonhadat list page."""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    all_a_tags = soup.find_all("a", href=True)
    links: Set[str] = set()

    for a in all_a_tags:
        href = a.get("href", "").strip()
        if not href or href == "#" or href.startswith("javascript:") or href.startswith("tel:"):
            continue

        full_url = href
        if full_url.startswith("/"):
            full_url = base_url.rstrip("/") + full_url

        if re.search(r"-\d{5,}\.html?", href):
            if not any(skip in href for skip in ["/trang--", "-t1.html", "-t2.html", "-t3.html", "/huong-dan", "/lien-he", "/quy-dinh"]):
                if full_url.startswith("http"):
                    links.add(full_url)

    return sorted(list(links))


def run_crawler(site: str, city: str, max_pages: int = 2, max_ads: int = 100, category: int = 1050):
    today_str = datetime.date.today().isoformat()

    # Route: Chotot API
    if site == "chotot":
        crawler = ChototCrawler()
        crawler.crawl(category=category, city=city, max_ads=max_ads, base_dir=BASE_DIR)
        return

    # Route: HTML Scraping for phongtro123 & alonhadat
    config_path = BASE_DIR / "config" / "sources.yaml"
    if not config_path.exists():
        logger.error(f"Config not found at {config_path}")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    site_cfg = config.get("sources", {}).get(site)
    if not site_cfg or not site_cfg.get("enabled"):
        logger.error(f"Site '{site}' is not configured or disabled.")
        return

    city_cfg = site_cfg.get("cities", {}).get(city)
    if not city_cfg:
        logger.error(f"City '{city}' not found for site '{site}'.")
        return

    base_url = site_cfg.get("base_url", "")
    start_url = city_cfg.get("start_url", "")
    page_pattern = city_cfg.get("page_pattern", "")
    rate_cfg = site_cfg.get("rate_limit", {})
    min_delay = rate_cfg.get("min_delay_sec", 1.0)
    max_delay = rate_cfg.get("max_delay_sec", 2.5)

    fetcher = PoliteFetcher(min_delay=min_delay, max_delay=max_delay)
    if base_url:
        fetcher.warmup(base_url)

    db_conn = init_db(BASE_DIR / "data" / "frontier.db")

    logger.info(f"=== Starting crawl for site={site}, city={city}, max_pages={max_pages if max_pages > 0 else 'ALL'} ===")

    # Stage A: Discovery
    page = 1
    consecutive_empty_pages = 0

    while True:
        if max_pages > 0 and page > max_pages:
            break

        if page == 1 and start_url:
            list_url = start_url
        else:
            list_url = page_pattern.format(page=page)

        logger.info(f"[Discovery] Fetching list page {page}{f'/{max_pages}' if max_pages > 0 else ''}: {list_url}")
        html = fetcher.fetch(list_url)
        if not html:
            logger.warning(f"[Discovery] Failed to fetch list page {page} at {list_url}")
            consecutive_empty_pages += 1
            if consecutive_empty_pages >= 3:
                logger.info("3 consecutive failed pages. Ending discovery phase.")
                break
            page += 1
            continue

        if site == "phongtro123":
            page_links = extract_list_links_phongtro123(html, base_url)
        else:
            page_links = extract_list_links_alonhadat(html, base_url)

        logger.info(f"[Discovery] Found {len(page_links)} detail links on page {page}")
        if not page_links:
            consecutive_empty_pages += 1
            if consecutive_empty_pages >= 2:
                logger.info("No more links found on consecutive pages. Discovery complete.")
                break
        else:
            consecutive_empty_pages = 0

        for link in page_links:
            db_conn.execute(
                """
                INSERT OR IGNORE INTO seen_urls (url, site, city, status)
                VALUES (?, ?, ?, 'discovered')
                """,
                (link, site, city),
            )
        db_conn.commit()
        page += 1

    # Stage B & D: Detail fetch and parse
    cur = db_conn.cursor()
    cur.execute(
        "SELECT url FROM seen_urls WHERE site=? AND city=? AND status='discovered'",
        (site, city),
    )
    pending_urls = [r[0] for r in cur.fetchall()]
    logger.info(f"=== Total pending detail URLs to fetch: {len(pending_urls)} ===")

    # Also load previously crawled URLs for this run's export
    cur.execute(
        "SELECT url FROM seen_urls WHERE site=? AND city=? AND status='crawled'",
        (site, city),
    )
    already_crawled_urls = [r[0] for r in cur.fetchall()]

    parsed_records = []

    # Re-parse existing raw HTML files if available
    for detail_url in already_crawled_urls:
        if site == "phongtro123":
            id_match = re.search(r"-pr(\d+)\.html", detail_url)
        else:
            id_match = re.search(r"-(\d+)\.html", detail_url)
        if id_match:
            listing_id = id_match.group(1)
            # Find in raw html
            raw_files = list((BASE_DIR / "data" / "raw" / "html" / site).glob(f"**/{listing_id}.html.gz"))
            if raw_files:
                import gzip
                with gzip.open(raw_files[0], "rt", encoding="utf-8") as f:
                    raw_html = f.read()
                if site == "phongtro123":
                    rec = parse_phongtro123_detail(raw_html, detail_url)
                else:
                    rec = parse_alonhadat_detail(raw_html, detail_url)
                rec["city"] = city
                rec["crawled_at"] = today_str
                parsed_records.append(rec)

    for idx, detail_url in enumerate(pending_urls, 1):
        logger.info(f"[{idx}/{len(pending_urls)}] Fetching detail: {detail_url}")
        detail_html = fetcher.fetch(detail_url)
        if not detail_html:
            db_conn.execute(
                "UPDATE seen_urls SET status='failed', error='fetch_failed' WHERE url=?",
                (detail_url,),
            )
            db_conn.commit()
            continue

        if site == "phongtro123":
            id_match = re.search(r"-pr(\d+)\.html", detail_url)
        else:
            id_match = re.search(r"-(\d+)\.html", detail_url)
        listing_id = id_match.group(1) if id_match else f"item_{idx}"

        # Save raw HTML
        fetcher.save_raw_html(detail_html, site, listing_id, today_str, BASE_DIR)

        # Parse record
        if site == "phongtro123":
            record = parse_phongtro123_detail(detail_html, detail_url)
        else:
            record = parse_alonhadat_detail(detail_html, detail_url)

        record["city"] = city
        record["crawled_at"] = datetime.datetime.now().isoformat()
        parsed_records.append(record)

        db_conn.execute(
            "UPDATE seen_urls SET status='crawled', crawled_at=? WHERE url=?",
            (datetime.datetime.now().isoformat(), detail_url),
        )
        db_conn.commit()

    # Persist parsed interim JSONL
    interim_dir = BASE_DIR / "data" / "interim"
    interim_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = interim_dir / f"parsed_{site}_{city}_{today_str}.jsonl"

    with open(jsonl_file, "w", encoding="utf-8") as f:
        for rec in parsed_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Export to both CSV and JSON formats
    file_prefix = f"raw_{site}_{city}"
    export_records(parsed_records, interim_dir, f"{file_prefix}_{today_str}")
    export_records(parsed_records, BASE_DIR, file_prefix)

    logger.info(
        f"=== Done! Exported {len(parsed_records)} listings to CSV & JSON for {site} ({city}) ==="
    )
    fetcher.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vietnam Rental Room Unified Crawler & Exporter CLI")
    parser.add_argument(
        "--site",
        type=str,
        required=True,
        choices=["phongtro123", "alonhadat", "chotot"],
        help="Target site (phongtro123, alonhadat, chotot)",
    )
    parser.add_argument(
        "--city",
        type=str,
        default="hanoi",
        choices=["hanoi", "hcm", "danang", "all"],
        help="Target city",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=2,
        help="Max listing pages to crawl (0 = ALL pages)",
    )
    parser.add_argument(
        "--max-ads",
        type=int,
        default=100,
        help="Max ads to crawl for Chotot API (0 = ALL ads)",
    )
    parser.add_argument(
        "--category",
        type=int,
        default=1050,
        help="Category ID for Chotot (1050 = Phòng trọ, 1010 = Căn hộ, 1020 = Nhà)",
    )
    args = parser.parse_args()
    run_crawler(
        site=args.site,
        city=args.city,
        max_pages=args.max_pages,
        max_ads=args.max_ads,
        category=args.category,
    )
