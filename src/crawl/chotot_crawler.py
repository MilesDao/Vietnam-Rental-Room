"""
src/crawl/chotot_crawler.py - Chotot Public API Crawler

Fetches structured room listings from gateway.chotot.com API:
GET https://gateway.chotot.com/v1/public/ad-listing?cg={category}&limit=20&o={offset}&st=u&region_v2={region}
"""

import datetime
import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

from src.parse.export import export_records

logger = logging.getLogger(__name__)

# Region codes: 12000 = Ha Noi, 13000 = TP.HCM, 10000 = Da Nang
REGION_MAP = {
    "hanoi": 12000,
    "hcm": 13000,
    "danang": 10000,
    "all": None,
}

# Category codes: 1050 = Phong tro, 1010 = Can ho chung cu, 1020 = Nha o
CATEGORY_MAP = {
    "phongtro": 1050,
    "canho": 1010,
    "nha": 1020,
}


class ChototCrawler:
    def __init__(self, min_delay: float = 0.8, max_delay: float = 1.8, timeout: float = 15.0):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.client = httpx.Client(
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://nha.chotot.com",
                "Referer": "https://nha.chotot.com/",
            },
        )

    def fetch_page(self, category: int = 1050, region_code: Optional[int] = None, offset: int = 0, limit: int = 20) -> Optional[Dict[str, Any]]:
        """Fetch a single page of ads from Chotot API."""
        time.sleep(random.uniform(self.min_delay, self.max_delay))
        params = {
            "cg": category,
            "limit": limit,
            "o": offset,
            "st": "u",
        }
        if region_code:
            params["region_v2"] = region_code

        url = "https://gateway.chotot.com/v1/public/ad-listing"
        try:
            r = self.client.get(url, params=params)
            if r.status_code == 200:
                return r.json()
            else:
                logger.error(f"Chotot API returned status {r.status_code} for offset={offset}")
                return None
        except Exception as e:
            logger.error(f"Network error fetching Chotot offset={offset}: {e}")
            return None

    def crawl(
        self,
        category: int = 1050,
        city: str = "hanoi",
        max_ads: int = 100,
        base_dir: Optional[Path] = None,
    ) -> List[Dict[str, Any]]:
        """
        Crawl listings from Chotot API up to max_ads (or all available) and export CSV/JSON.
        """
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent.parent.parent

        region_code = REGION_MAP.get(city)
        logger.info(f"=== Starting Chotot crawl: category={category}, city={city} (region={region_code}), max_ads={max_ads} ===")

        all_ads: List[Dict[str, Any]] = []
        offset = 0
        limit = 20
        total_available = None

        while True:
            if max_ads > 0 and len(all_ads) >= max_ads:
                break

            logger.info(f"[Chotot] Fetching ads offset={offset} (Collected: {len(all_ads)}/{max_ads if max_ads > 0 else 'ALL'})...")
            data = self.fetch_page(category=category, region_code=region_code, offset=offset, limit=limit)
            if not data:
                break

            ads = data.get("ads", [])
            if not ads:
                logger.info("[Chotot] No more ads returned. Crawl finished.")
                break

            if total_available is None:
                total_available = data.get("total", len(ads))
                logger.info(f"[Chotot] Total listings reported by API: {total_available}")

            all_ads.extend(ads)
            offset += len(ads)

            # Chotot elasticsearch window limit is 10,000
            if offset >= 10000 or (total_available and offset >= total_available):
                break

        if max_ads > 0:
            all_ads = all_ads[:max_ads]

        # Export raw responses
        today_str = datetime.date.today().isoformat()
        interim_dir = base_dir / "data" / "interim"
        file_prefix = f"raw_chotot_cg{category}_{city}_{today_str}"

        # Export both JSON and CSV
        export_records(all_ads, interim_dir, file_prefix)
        # Also export to workspace root if requested
        export_records(all_ads, base_dir, f"raw_chotot_cg{category}_{city}")

        logger.info(f"=== Chotot crawl complete! Total ads: {len(all_ads)} ===")
        return all_ads
