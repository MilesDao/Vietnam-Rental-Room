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

    # Native ID from URL (e.g. ...-19056845.html)
    native_id_match = re.search(r"-(\d+)\.html", url)
    native_id = native_id_match.group(1) if native_id_match else "unknown"

    # Title
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""

    # Price & Area
    price_elem = soup.select_one(".moreinfor .price .value, .price .value, .detail .price, .property-price, .price")
    price_raw = price_elem.get_text(strip=True) if price_elem else ""
    price_vnd, is_negotiable = parse_price(price_raw)

    area_elem = soup.select_one(".moreinfor .square .value, .square .value, .detail .square, .property-area, .square, .acreage")
    area_raw = area_elem.get_text(strip=True) if area_elem else ""
    area_m2 = parse_area(area_raw)

    # Fallback search for price & area
    if price_vnd is None and not is_negotiable:
        for tag in soup.find_all(["div", "span", "p", "td"]):
            t = tag.get_text(" ", strip=True)
            if any(k in t for k in ["Giá:", "Mức giá:"]) and len(t) < 100:
                p, neg = parse_price(t)
                if p or neg:
                    price_vnd, is_negotiable = p, neg
                    break

    if area_m2 is None:
        for tag in soup.find_all(["div", "span", "p", "td"]):
            t = tag.get_text(" ", strip=True)
            if any(k in t for k in ["Diện tích:", "DT:"]) and len(t) < 100:
                a = parse_area(t)
                if a:
                    area_m2 = a
                    break

    # Address
    address_raw = ""
    addr_elem = soup.select_one(".address .value, .property .address, .property-address, .address")
    if addr_elem:
        address_raw = addr_elem.get_text(strip=True)
    if not address_raw:
        for tag in soup.find_all(["div", "p", "span", "td"]):
            t = tag.get_text(" ", strip=True)
            if "Địa chỉ:" in t and len(t) < 250:
                m = re.search(r"Địa chỉ:\s*(.+)", t)
                if m:
                    address_raw = m.group(1).strip()
                    break

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
    date_elem = soup.select_one(".moreinfor .date .value, .date .value, .property-date, .date")
    posted_at_raw = date_elem.get_text(strip=True) if date_elem else ""

    # Image URLs (up to 8 images)
    images: List[str] = []
    for img in soup.select("img.limage, img[src*='/files/properties/']"):
        src = img.get("src") or img.get("data-src")
        if src and "thumbnails" not in str(src):
            if str(src).startswith("/"):
                src = "https://alonhadat.com.vn" + str(src)
            if src not in images and not any(logo in str(src) for logo in ["logo", "icon", "banner", "check", "gotop"]):
                images.append(str(src))
                if len(images) >= 8:
                    break

    # Phone Hash
    phone_raw = ""
    for a in soup.find_all("a", href=True):
        if a["href"].startswith("tel:"):
            phone_raw = a["href"].replace("tel:", "").strip()
            break
    if not phone_raw:
        for elem in soup.find_all(["span", "div", "a", "td"]):
            t = elem.get_text(strip=True)
            match = re.search(r"(0\d{9,10})", t)
            if match:
                phone_raw = match.group(1)
                break

    phone_hash = ""
    if phone_raw:
        phone_clean = re.sub(r"\D", "", phone_raw)
        if phone_clean:
            phone_hash = hashlib.sha256((phone_clean + PROJECT_SALT).encode("utf-8")).hexdigest()

    return {
        "listing_id": f"alonhadat_{native_id}",
        "source": "alonhadat",
        "url": url,
        "title": title,
        "description": description,
        "price_vnd_month": price_vnd,
        "price_is_negotiable": is_negotiable,
        "area_m2": area_m2,
        "address_raw": address_raw,
        "room_type": "phòng trọ",
        "posted_at_raw": posted_at_raw,
        "phone_hash": phone_hash,
        "image_urls": images,
        "n_images": len(images),
    }
