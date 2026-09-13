"""
src/crawl/run.py - Fast & Resilient Crawler Runner & Exporter CLI for Phongtro123 & Alonhadat

Enforces constraints:
  - Strictly Phòng Trọ / Rental Rooms (excludes Chung cư cao cấp, Biệt thự, Nhà nguyên căn, ...)
  - Maximum price <= 6,000,000 VND / month
  - Fast concurrent detail fetching (3-5 workers) with polite jittered delay
  - Scoped crawl: Only fetches details for listings discovered in the requested page range

Output:
  - Compressed raw HTML in data/raw/html/
  - JSON Lines (.jsonl) in data/interim/
  - JSON Array (.json) in data/interim/ and workspace root
  - Flat tabular CSV (.csv with UTF-8 BOM for Excel) in data/interim/ and workspace root
"""

import argparse
import datetime
import json
import logging
import re
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Set, Tuple
from bs4 import BeautifulSoup
import yaml

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.crawl.fetcher import PoliteFetcher
from src.parse.phongtro123_parser import parse_phongtro123_detail
from src.parse.export import save_site_dataset
from src.parse.filter import is_valid_rental_room, is_listing_expired, MAX_RENTAL_PRICE_VND

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("crawl_runner")

db_lock = threading.Lock()


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize SQLite frontier database for tracking seen URLs."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
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


def extract_list_links_phongtro123(html: str, base_url: str, include_expired: bool = False) -> List[str]:
    """Extract detail listing URLs from a phongtro123 list page."""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    links: Set[str] = set()
    # Check individual post items
    post_cards = soup.select("ul.post__listing > li, .post-item, .item-post, article")
    if post_cards:
        for card in post_cards:
            card_text = card.get_text(" ", strip=True).lower()
            if not include_expired:
                if any(exp in card_text for exp in ["hết hạn", "đã cho thuê", "đã thuê", "ngừng giao dịch", "tin cũ"]):
                    continue
            for a in card.find_all("a", href=True):
                href = a["href"].strip()
                if "-pr" in href and ".html" in href:
                    if href.startswith("/"):
                        href = base_url.rstrip("/") + href
                    if href.startswith("http"):
                        links.add(href)

    # Fallback to direct anchor search if selector matched nothing
    if not links:
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if "-pr" in href and ".html" in href:
                if href.startswith("/"):
                    href = base_url.rstrip("/") + href
                if href.startswith("http"):
                    links.add(href)

    return sorted(list(links))


def extract_list_links_alonhadat(html: str, base_url: str, include_expired: bool = False) -> List[str]:
    """Extract detail listing URLs from an alonhadat list page."""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    links: Set[str] = set()
    property_cards = soup.select(".property-item, .content-item, .box-item, div.item, li")
    if property_cards:
        for card in property_cards:
            card_text = card.get_text(" ", strip=True).lower()
            if not include_expired:
                if any(exp in card_text for exp in ["hết hạn", "đã cho thuê", "đã giao dịch", "ngừng giao dịch"]):
                    continue
            for a in card.find_all("a", href=True):
                href = a.get("href", "").strip()
                if re.search(r"-\d{5,}\.html?", href):
                    if not any(skip in href for skip in ["/trang-", "-t1.html", "-t2.html", "-t3.html", "/huong-dan", "/lien-he", "/quy-dinh"]):
                        full_url = base_url.rstrip("/") + href if href.startswith("/") else href
                        if full_url.startswith("http"):
                            links.add(full_url)

    if not links:
        all_a_tags = soup.find_all("a", href=True)
        for a in all_a_tags:
            href = a.get("href", "").strip()
            if not href or href == "#" or href.startswith("javascript:") or href.startswith("tel:"):
                continue

            full_url = base_url.rstrip("/") + href if href.startswith("/") else href
            if re.search(r"-\d{5,}\.html?", href):
                if not any(skip in href for skip in ["/trang-", "-t1.html", "-t2.html", "-t3.html", "/huong-dan", "/lien-he", "/quy-dinh"]):
                    if full_url.startswith("http"):
                        links.add(full_url)

    return sorted(list(links))


def fetch_and_parse_worker(
    detail_url: str,
    site: str,
    city: str,
    today_str: str,
    max_price: float,
    min_delay: float,
    max_delay: float,
    include_expired: bool = False,
    allow_negotiable: bool = False,
) -> Tuple[Optional[dict], Optional[str], str]:
    """
    Fetch raw HTML, check expiration (if not include_expired), persist compressed fixture, parse structured dict, and apply filter.
    Returns: (parsed_record or None, skip_reason or None, detail_url)
    """
    fetcher = PoliteFetcher(min_delay=min_delay, max_delay=max_delay)
    try:
        detail_html = fetcher.fetch(detail_url)
        if not detail_html:
            return None, "fetch_failed", detail_url

        # 1. Check if listing is expired / closed / deleted (when include_expired=False)
        if not include_expired:
            is_exp, exp_reason = is_listing_expired(detail_html)
            if is_exp:
                return None, f"Expired: {exp_reason}", detail_url

        if site == "phongtro123":
            id_match = re.search(r"-pr(\d+)\.html?", detail_url)
            if not id_match:
                id_match = re.search(r"pr(\d+)", detail_url)
        else:
            id_match = re.search(r"-(\d+)\.html?", detail_url)
            if not id_match:
                id_match = re.search(r"(\d+)\.html?", detail_url)
        listing_id = id_match.group(1) if id_match else f"item_{abs(hash(detail_url)) % 1000000}"

        # Save compressed raw HTML fixture
        fetcher.save_raw_html(detail_html, site, listing_id, today_str, BASE_DIR)

        # Parse structured record
        if site == "phongtro123":
            record = parse_phongtro123_detail(detail_html, detail_url)
        else:
            return None, f"Unsupported site parser: {site}", detail_url

        record["city"] = "hanoi" if "hanoi" in city else ("hcm" if "hcm" in city else city)
        record["crawled_at"] = datetime.datetime.now().isoformat()
        from src.parse.normalizer import enrich_record
        record = enrich_record(record)

        # Validate property type, price cap, and price specificity
        is_valid, reason = is_valid_rental_room(record, max_price=max_price, allow_negotiable=allow_negotiable)
        if is_valid:
            return record, None, detail_url
        else:
            return None, reason, detail_url
    finally:
        fetcher.close()


def run_crawler(
    site: str,
    city: str,
    max_pages: int = 2,
    start_page: int = 1,
    max_price: float = MAX_RENTAL_PRICE_VND,
    include_expired: bool = False,
    allow_negotiable: bool = False,
    reset_filtered: bool = False,
):
    today_str = datetime.date.today().isoformat()

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
    min_delay = rate_cfg.get("min_delay_sec", 0.3)
    max_delay = rate_cfg.get("max_delay_sec", 0.8)
    concurrency = rate_cfg.get("max_concurrency", 3)

    discovery_fetcher = PoliteFetcher(min_delay=min_delay, max_delay=max_delay)
    if base_url:
        discovery_fetcher.warmup(base_url)

    db_conn = init_db(BASE_DIR / "data" / "frontier.db")
    price_str = f"<= {max_price:,.0f} VND" if max_price is not None else "ALL PRICES (No Limit)"
    logger.info(f"=== Starting crawl: site={site}, city={city}, start_page={start_page}, max_pages={max_pages if max_pages > 0 else 'ALL'}, max_price={price_str} ===")

    # Stage A: Discovery
    page = start_page
    consecutive_empty_pages = 0
    discovered_in_this_run: List[str] = []
    detected_max_pages: Optional[int] = None

    while True:
        if max_pages > 0 and page > max_pages:
            break
        if detected_max_pages and page > detected_max_pages:
            logger.info(f"Reached detected maximum page limit ({detected_max_pages}) for {site} ({city}). Ending discovery.")
            break

        if page == 1 and start_url:
            list_url = start_url
        else:
            list_url = page_pattern.format(page=page)

        logger.info(f"[Discovery] Fetching list page {page}{f'/{detected_max_pages or max_pages}' if (detected_max_pages or max_pages > 0) else ''}: {list_url}")
        html = discovery_fetcher.fetch(list_url)
        if not html:
            logger.warning(f"[Discovery] Failed to fetch list page {page} at {list_url}")
            consecutive_empty_pages += 1
            if consecutive_empty_pages >= 3:
                logger.info("3 consecutive failed pages. Ending discovery phase.")
                break
            page += 1
            continue

        # On first page, automatically detect the true pagination upper bound for this city
        if page == 1 and max_pages == 0:
            try:
                soup_d = BeautifulSoup(html, "html.parser")
                p_links = soup_d.select("a[href*='page='], a[href*='trang-'], .pagination a, .page a")
                all_found_pages = []
                for a_tag in p_links:
                    href = a_tag.get("href", "")
                    m_p = re.findall(r"(?:page=|trang-)(\d+)", href)
                    if m_p:
                        all_found_pages.append(int(m_p[-1]))
                if all_found_pages:
                    detected_max_pages = max(all_found_pages)
                    logger.info(f"🎯 Auto-detected true maximum page limit for {site} ({city}): {detected_max_pages} pages")
            except Exception as e:
                logger.debug(f"Could not auto-detect max pages: {e}")

        if site == "phongtro123":
            page_links = extract_list_links_phongtro123(html, base_url, include_expired=include_expired)
        else:
            page_links = extract_list_links_alonhadat(html, base_url, include_expired=include_expired)

        logger.info(f"[Discovery] Found {len(page_links)} detail links on page {page}")
        if not page_links:
            consecutive_empty_pages += 1
            if consecutive_empty_pages >= 2:
                logger.info("No more links found on consecutive pages. Discovery complete.")
                break
        else:
            consecutive_empty_pages = 0

        for link in page_links:
            if link not in discovered_in_this_run:
                discovered_in_this_run.append(link)
            with db_lock:
                db_conn.execute(
                    """
                    INSERT OR IGNORE INTO seen_urls (url, site, city, status)
                    VALUES (?, ?, ?, 'discovered')
                    """,
                    (link, site, city),
                )
        with db_lock:
            db_conn.commit()
        page += 1

    discovery_fetcher.close()

    # Reset filtered_out URLs if requested or crawling all historical pages
    if reset_filtered or include_expired:
        with db_lock:
            db_conn.execute(
                """
                UPDATE seen_urls
                SET status='discovered'
                WHERE site=? AND city=? AND status='filtered_out' AND (error LIKE 'Expired%' OR error LIKE 'Alert%')
                """,
                (site, city),
            )
            db_conn.commit()

    # Determine which URLs to fetch:
    # If max_pages > 0: only fetch links discovered in this run to ensure fast and scoped execution.
    # If max_pages == 0: fetch all pending discovered URLs in database.
    if max_pages > 0:
        pending_urls = discovered_in_this_run
    else:
        cur = db_conn.cursor()
        cur.execute(
            "SELECT url FROM seen_urls WHERE site=? AND city=? AND status='discovered'",
            (site, city),
        )
        pending_urls = [r[0] for r in cur.fetchall()]

    logger.info(f"=== Detail Extraction: Fetching {len(pending_urls)} listings with {concurrency} workers ===")

    parsed_records = []
    skipped_count = 0
    completed_count = 0

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_to_url = {
            executor.submit(
                fetch_and_parse_worker,
                url,
                site,
                city,
                today_str,
                max_price,
                min_delay,
                max_delay,
                include_expired,
                allow_negotiable,
            ): url
            for url in pending_urls
        }

        for future in as_completed(future_to_url):
            url = future_to_url[future]
            completed_count += 1
            try:
                record, skip_reason, detail_url = future.result()
                if record:
                    parsed_records.append(record)
                    p_val = record.get('price_vnd_month')
                    p_str = f"{p_val/1e6:.1f}M" if isinstance(p_val, (int, float)) else str(p_val or "N/A")
                    logger.info(f"[{completed_count}/{len(pending_urls)}] ✅ [OK] {record['listing_id']}: {p_str} - '{record.get('title', '')[:35]}'")
                    with db_lock:
                        db_conn.execute(
                            "UPDATE seen_urls SET status='crawled', crawled_at=? WHERE url=?",
                            (datetime.datetime.now().isoformat(), detail_url),
                        )
                else:
                    skipped_count += 1
                    logger.info(f"[{completed_count}/{len(pending_urls)}] ⏭️ [Excluded] {skip_reason} ({url})")
                    with db_lock:
                        db_conn.execute(
                            "UPDATE seen_urls SET status='filtered_out', crawled_at=?, error=? WHERE url=?",
                            (datetime.datetime.now().isoformat(), skip_reason, detail_url),
                        )
                with db_lock:
                    db_conn.commit()
            except Exception as exc:
                logger.error(f"Error fetching {url}: {exc}")
                with db_lock:
                    db_conn.execute(
                        "UPDATE seen_urls SET status='failed', error=? WHERE url=?",
                        (str(exc), url),
                    )
                    db_conn.commit()

    logger.info(f"=== Crawl Completed: {len(parsed_records)} valid phòng trọ retained ({price_str}), {skipped_count} excluded ===")

    # Overwrite the single raw_{site}.json and raw_{site}.csv in workspace root
    save_site_dataset(parsed_records, BASE_DIR, site)

    logger.info(
        f"=== Done! Saved/Overwritten raw_{site}.csv & raw_{site}.json with {len(parsed_records)} listings for {site} ({city}) ==="
    )
    db_conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vietnam Rental Room Fast Concurrent Crawler & Exporter CLI")
    parser.add_argument(
        "--site",
        type=str,
        required=True,
        choices=["phongtro123", "alonhadat"],
        help="Target site (phongtro123, alonhadat)",
    )
    parser.add_argument(
        "--city",
        type=str,
        default="hanoi",
        help="Target city or category key from sources.yaml (e.g. hanoi, hanoi_ccmn, hanoi_oghep, hcm)",
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
        default=2,
        help="Max listing pages to crawl (0 = ALL pages)",
    )
    parser.add_argument(
        "--max-price",
        type=float,
        default=MAX_RENTAL_PRICE_VND,
        help="Max price in VND/month (default: 6,000,000 VND)",
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
        default=True,
        help="Allow listings with negotiable / unspecified prices (default: True)",
    )
    parser.add_argument(
        "--reset-filtered",
        action="store_true",
        default=False,
        help="Reset previously filtered expired URLs in SQLite frontier to discovered",
    )
    args = parser.parse_args()
    run_crawler(
        site=args.site,
        city=args.city,
        start_page=args.start_page,
        max_pages=args.max_pages,
        max_price=args.max_price,
        include_expired=args.include_expired,
        allow_negotiable=args.allow_negotiable,
        reset_filtered=args.reset_filtered,
    )
