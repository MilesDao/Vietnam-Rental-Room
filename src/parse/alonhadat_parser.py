"""
src/parse/alonhadat_parser.py - Pure Function Parser for alonhadat.com.vn

Extracts structured listing attributes from alonhadat raw HTML into canonical schema.
"""

import hashlib
import re
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
from src.parse.phongtro123_parser import parse_price, parse_area, PROJECT_SALT


def parse_alonhadat_detail(html_content: str, url: str) -> Dict[str, Any]:
    """
    Parse a single listing detail HTML page from alonhadat.com.vn into canonical dict.
    """
    try:
        soup = BeautifulSoup(html_content, "lxml")
    except Exception:
        soup = BeautifulSoup(html_content, "html.parser")

    # Native ID from URL (e.g. ...-19056845.html or /19056845.html)
    native_id_match = re.search(r"-(\d+)\.html?", url)
    if not native_id_match:
        native_id_match = re.search(r"(\d+)\.html?", url)
    if not native_id_match:
        native_id_match = re.search(r"(\d+)", url)
    native_id = native_id_match.group(1) if native_id_match else "unknown"

    # Title
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""

    # Price extraction (Priority: Schema.org microdata inside section.more-info)
    price = None

    price_data = soup.select_one("section.more-info data[itemprop='price'], data[itemprop='price']")
    if price_data and price_data.get("value"):
        try:
            price = round(float(price_data["value"]))
        except (ValueError, TypeError):
            pass

    if price is None:
        price_elem = soup.select_one("section.more-info .price, .more-info span.price")
        if price_elem:
            price = parse_price(price_elem.get_text(strip=True))

    if price is None:
        # Fallback: scan description or title for price
        price = parse_price(title)

    # Area extraction (Priority: Schema.org microdata inside section.more-info)
    area_m2 = None
    area_data = soup.select_one("section.more-info span[itemprop='value'], section.more-info .area [itemprop='value']")
    if area_data:
        try:
            area_m2 = round(float(area_data.get_text(strip=True).replace(",", ".")), 2)
        except (ValueError, TypeError):
            pass

    if area_m2 is None:
        area_elem = soup.select_one("section.more-info .area, .more-info span.area")
        if area_elem:
            area_m2 = parse_area(area_elem.get_text(strip=True))

    if area_m2 is None:
        # Fallback: scan title for area (e.g. 25m2, 30m2)
        area_m2 = parse_area(title)

    # Address (Current real address container)
    address_raw = ""
    addr_elem = soup.select_one("address.current-address, .address-label + address, address")
    if addr_elem:
        address_raw = addr_elem.get_text(" ", strip=True)
    if not address_raw:
        old_addr = soup.select_one("p.old-address")
        if old_addr:
            address_raw = old_addr.get_text(" ", strip=True)

    # Description (real content inside section.detail.text-content)
    description = ""
    sec = soup.select_one("section.detail.text-content, .detail.text-content, .text-content")
    if sec:
        description = sec.get_text("\n", strip=True).replace("Thông tin chi tiết", "").strip()
    if not description:
        desc_elem = soup.select_one(".property-description, .detail-text")
        if desc_elem:
            description = desc_elem.get_text("\n", strip=True)

    # Posted date
    time_elem = soup.select_one("header.title time.date, header.title time, time.date")
    posted_at_raw = time_elem.get_text(strip=True) if time_elem else ""

    # Image URLs (up to 8 images, avoiding default avatars / logos)
    images: List[str] = []
    for img in soup.select("img.limage, img[src*='/files/properties/']"):
        src = img.get("src") or img.get("data-src")
        if src and "thumbnails" not in str(src) and not any(skip in str(src) for skip in ["logo", "icon", "banner", "check", "gotop"]):
            if str(src).startswith("/"):
                src = "https://alonhadat.com.vn" + str(src)
            if src not in images:
                images.append(str(src))
                if len(images) >= 8:
                    break

    # Phone Hash (Salted Hash)
    phone_number = ""
    for a in soup.find_all("a", href=True):
        if a["href"].startswith("tel:"):
            phone_number = a["href"].replace("tel:", "").strip()
            break
    if not phone_number:
        for elem in soup.find_all(["span", "div", "a", "td", "p"]):
            t = elem.get_text(strip=True)
            match = re.search(r"(0\d{9,10})", t)
            if match:
                phone_number = match.group(1)
                break

    rec = {
        "listing_id": f"alonhadat_{native_id}",
        "source": "alonhadat",
        "url": url,
        "title": title,
        "description": description,
        "price_vnd": price,
        "area_m2": area_m2,
        "address_raw": address_raw,
        "room_type": "phòng trọ",
        "posted_at_raw": posted_at_raw,
        "phone_number": phone_number,
        "image_urls": images,
        "n_images": len(images),
    }
    from src.parse.normalizer import enrich_record
    return enrich_record(rec)
