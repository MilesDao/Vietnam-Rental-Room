from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Any
from bs4 import BeautifulSoup

def parse_list_page(html: str, base_url: str = "https://batdongsan.com.vn") -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict[str, Any]] = []
    
    # Try multiple common selectors
    cards = soup.select("a.js__product-link-for-product-id, a.re__link-se")
    
    # Fallback to regex if classes changed
    if not cards:
        cards = soup.find_all("a", href=re.compile(r'-pr\d+/?$'))
        
    for card in cards:
        url = card.get("href")
        if not url:
            continue
        if url.startswith("/"):
            url = base_url.rstrip("/") + url
            
        title_el = card.select_one(".pr-title")
        title = title_el.get_text(strip=True) if title_el else None
        
        # We only really need the URL and listing ID to fetch details
        # The listing ID on batdongsan usually is at the end of the URL like "pr12345"
        # Or we can just hash the URL as the listing ID if not found easily.
        m = re.search(r'pr(\d+)', url)
        native_id = m.group(1) if m else str(hash(url))
        
        rows.append({
            "listing_id": f"bds_{native_id}",
            "url": url,
            "title": title
        })
    
    return rows

def parse_detail_page(html: str, url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    
    m = re.search(r'pr(\d+)', url)
    native_id = m.group(1) if m else str(hash(url))
    
    title_el = soup.select_one("h1.pr-title")
    title = title_el.get_text(strip=True) if title_el else None
    
    address_el = soup.select_one("span.js__pr-address")
    address = address_el.get_text(strip=True) if address_el else None
    
    price_el = soup.select_one("span.js__pr-price")
    price_raw = price_el.get_text(strip=True) if price_el else None
    
    area_el = soup.select_one("span.js__pr-area")
    area_raw = area_el.get_text(strip=True) if area_el else None
    
    desc_el = soup.select_one("div.re__detail-content")
    description = desc_el.get_text(separator="\n", strip=True) if desc_el else None
    
    # Breadcrumbs for district
    district = None
    breadcrumb_links = soup.select(".re__breadcrumb a")
    if len(breadcrumb_links) >= 3:
        district = breadcrumb_links[2].get_text(strip=True)
    
    # Images
    image_urls = []
    for img in soup.select("div.swiper-slide img"):
        src = img.get("data-src") or img.get("src")
        if src and "http" in src:
            image_urls.append(src)
            
    # Phone
    phone = None
    phone_el = soup.select_one("span.js__phone")
    if phone_el and phone_el.get("raw"):
        phone = phone_el.get("raw")
    elif phone_el:
        phone = phone_el.get_text(strip=True)
        
    poster_name = None
    poster_el = soup.select_one("div.re__contact-name")
    if poster_el:
        poster_name = poster_el.get("title") or poster_el.get_text(strip=True)

    return {
        "listing_id": f"bds_{native_id}",
        "source": "batdongsan",
        "url": url,
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "description": description,
        "room_type": "phong_tro",
        "price_raw": price_raw,
        "area_raw": area_raw,
        "address_raw": address,
        "province": "Hà Nội" if "Hà Nội" in (address or "") or "Ha Noi" in (address or "") else None,
        "district": district,
        "n_images": len(image_urls),
        "image_urls": image_urls,
        "poster_name": poster_name,
        "phone": phone
    }
