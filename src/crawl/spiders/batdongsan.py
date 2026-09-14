from __future__ import annotations
import logging
from src.parse.batdongsan_parser import parse_list_page

log = logging.getLogger(__name__)

def list_page_url(base_url: str, category_path: str, page: int) -> str:
    # Batdongsan format: https://batdongsan.com.vn/cho-thue-phong-tro-nha-tro-ha-noi/p2
    path = category_path
    if page > 1:
        path = f"{path}/p{page}"
    url = f"{base_url.rstrip('/')}/{path}"
    return url

def iter_list_pages(
    fetcher, # This will be the BrowserFetcher
    base_url: str,
    category_path: str,
    start_page: int = 1,
    max_pages: int | None = None,
):
    page = start_page
    while max_pages is None or page < start_page + max_pages:
        url = list_page_url(base_url, category_path, page)
        html = fetcher.get(url)
        rows = parse_list_page(html, base_url=base_url)
        
        if not rows:
            log.info("slice exhausted at page %d (%s)", page, url)
            return
            
        yield page, rows
        page += 1
