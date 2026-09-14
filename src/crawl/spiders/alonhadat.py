"""Discovery spider for alonhadat.com.vn's phong-tro (rental room) category."""
from __future__ import annotations

import logging

from src.crawl.fetcher import Fetcher
from src.parse.alonhadat_parser import parse_list_page

log = logging.getLogger(__name__)


def list_page_url(base_url: str, category_path: str, province_slug: str, page: int) -> str:
    """alonhadat paginates via a path segment, not a query param.

    Page 1: https://alonhadat.com.vn/<category>/<province>
    Page N: https://alonhadat.com.vn/<category>/<province>/trang-<N>
    (confirmed via the page's own `<link rel='next'>` -- docs/alonhadat_scraping.md)
    """
    url = f"{base_url.rstrip('/')}/{category_path}/{province_slug}"
    if page > 1:
        url += f"/trang-{page}"
    return url


def iter_list_pages(
    fetcher: Fetcher,
    base_url: str,
    category_path: str,
    province_slug: str,
    start_page: int = 1,
    max_pages: int | None = None,
):
    """Yield (page_number, rows) for one province x category slice, lazily.

    Same generator shape as src/crawl/spiders/mogi.py's iter_list_pages(), for
    the same reason: interleave discovery with detail fetching rather than
    buffering a whole province first. alonhadat's inventory is far smaller
    than mogi's (~1,900 listings nationwide vs. mogi's ~30k in HCMC alone --
    docs/alonhadat_scraping.md), so this matters less here, but there is still
    no result count or last-page link, so an empty page remains the only
    end-of-slice signal.
    """
    page = start_page
    while max_pages is None or page < start_page + max_pages:
        url = list_page_url(base_url, category_path, province_slug, page)
        rows = parse_list_page(fetcher.get(url).text, base_url=base_url)
        if not rows:
            log.info("slice exhausted at page %d (%s)", page, url)
            return
        yield page, rows
        page += 1
