"""Discovery spider for mogi.vn's phong-tro (rental room) category."""
from __future__ import annotations

import logging

from src.crawl.fetcher import Fetcher
from src.parse.mogi_parser import parse_list_page

log = logging.getLogger(__name__)


def list_page_url(base_url: str, category_path: str, city_slug: str | None, page: int) -> str:
    path = f"{city_slug}/{category_path}" if city_slug else category_path
    url = f"{base_url.rstrip('/')}/{path}"
    if page > 1:
        url += f"?cp={page}"
    return url


def discover_detail_rows(
    fetcher: Fetcher,
    base_url: str,
    category_path: str,
    city_slug: str | None,
    max_pages: int,
) -> list[dict]:
    """Walk paginated list pages for one city, returning deduped card rows."""
    seen: set[str] = set()
    rows: list[dict] = []
    for page in range(1, max_pages + 1):
        url = list_page_url(base_url, category_path, city_slug, page)
        resp = fetcher.get(url)
        page_rows = parse_list_page(resp.text, base_url=base_url)
        if not page_rows:
            log.info("no cards found on page %d (%s) -- stopping, likely past last page", page, url)
            break
        new = 0
        for row in page_rows:
            if row["listing_id"] in seen:
                continue
            seen.add(row["listing_id"])
            rows.append(row)
            new += 1
        log.info("page %d: %d cards, %d new", page, len(page_rows), new)
        if new == 0:
            break
    return rows


def iter_list_pages(
    fetcher: Fetcher,
    base_url: str,
    category_path: str,
    city_slug: str | None,
    start_page: int = 1,
    max_pages: int | None = None,
):
    """Yield (page_number, rows) for one province x category slice, lazily.

    Unlike discover_detail_rows() this does not buffer the whole slice before
    returning: mogi's big provinces run past 2000 pages, so the caller needs to
    interleave detail fetching with discovery and checkpoint as it goes.

    Terminates on the first page that yields no cards -- mogi publishes no
    result count and its pager is a sliding window with no last-page link, so
    an empty page is the only end-of-slice signal available.
    """
    page = start_page
    while max_pages is None or page < start_page + max_pages:
        url = list_page_url(base_url, category_path, city_slug, page)
        rows = parse_list_page(fetcher.get(url).text, base_url=base_url)
        if not rows:
            log.info("slice exhausted at page %d (%s)", page, url)
            return
        yield page, rows
        page += 1
