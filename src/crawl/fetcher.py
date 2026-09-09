"""
src/crawl/fetcher.py - Polite Robust HTTP Fetcher

Provides HTTP request handling with rate limiting (jittered delay),
exponential backoff on retryable status codes, User-Agent rotation,
and raw HTML/image storage helpers.
"""

import gzip
import logging
import random
import time
from pathlib import Path
from typing import Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


class PoliteFetcher:
    """
    HTTP Fetcher with jittered delays, automatic exponential backoff,
    cookie persistence, session warmup, and storage utilities.
    """

    def __init__(
        self,
        min_delay: float = 1.0,
        max_delay: float = 2.5,
        timeout: float = 20.0,
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.timeout = timeout
        self.client = httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"macOS"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
        )

    def warmup(self, base_url: str):
        """Warm up session cookies by visiting the homepage first."""
        try:
            logger.info(f"Warming up session at {base_url}...")
            self.client.get(base_url, headers={"User-Agent": random.choice(DEFAULT_USER_AGENTS)})
        except Exception as e:
            logger.warning(f"Warmup warning for {base_url}: {e}")

    def fetch(self, url: str, max_retries: int = 3) -> Optional[str]:
        """
        Fetch HTML text for a given URL with polite delay and exponential backoff retry.
        """
        # Apply polite randomized jitter delay
        delay = random.uniform(self.min_delay, self.max_delay)
        time.sleep(delay)

        headers = {"User-Agent": random.choice(DEFAULT_USER_AGENTS)}

        for attempt in range(1, max_retries + 1):
            try:
                response = self.client.get(url, headers=headers)
                if response.status_code == 200:
                    return response.text
                elif response.status_code in (429, 500, 502, 503, 504):
                    backoff = (2 ** attempt) + random.uniform(0.5, 1.5)
                    logger.warning(
                        f"HTTP {response.status_code} for {url}. "
                        f"Backoff {backoff:.2f}s (Attempt {attempt}/{max_retries})"
                    )
                    time.sleep(backoff)
                else:
                    logger.error(
                        f"Failed to fetch {url}, status code: {response.status_code}"
                    )
                    return None
            except httpx.RequestError as exc:
                backoff = (2 ** attempt) + random.uniform(0.5, 1.0)
                logger.warning(
                    f"Network error requesting {url}: {exc}. "
                    f"Retrying in {backoff:.2f}s..."
                )
                time.sleep(backoff)

        logger.error(f"Exceeded max retries ({max_retries}) for {url}")
        return None

    def fetch_bytes(self, url: str, max_retries: int = 3) -> Optional[bytes]:
        """
        Fetch raw binary content (e.g. images) with retry support.
        """
        headers = {"User-Agent": random.choice(DEFAULT_USER_AGENTS)}
        for attempt in range(1, max_retries + 1):
            try:
                response = self.client.get(url, headers=headers)
                if response.status_code == 200:
                    return response.content
                time.sleep(1.0 * attempt)
            except httpx.RequestError:
                time.sleep(1.0 * attempt)
        return None

    def save_raw_html(
        self,
        html: str,
        site: str,
        listing_id: str,
        date_str: str,
        base_dir: Path,
    ) -> Path:
        """
        Persist raw HTML content as a compressed .html.gz file.
        Path: data/raw/html/<site>/<date>/<listing_id>.html.gz
        """
        out_dir = base_dir / "data" / "raw" / "html" / site / date_str
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{listing_id}.html.gz"
        with gzip.open(out_file, "wt", encoding="utf-8") as f:
            f.write(html)
        logger.debug(f"Saved raw HTML: {out_file}")
        return out_file

    def close(self):
        """Close the underlying HTTP client session."""
        self.client.close()
