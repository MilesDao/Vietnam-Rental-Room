"""
src/parse/phongtro123_parser.py - Pure Function Parser for phongtro123.com

Extracts structured listing attributes from raw HTML string into canonical schema.
"""

import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

PROJECT_SALT = "VN_RENTAL_ROOM_2026_SECRET_SALT"


def parse_price(price_text: str) -> Any:
    """
    Parse Vietnamese price string to float (VND/month) or negotiable text.
    Examples:
        - "3.5 triệu/tháng", "3,5 tr", "3tr5", "3 triệu 5" -> 3500000.0
        - "800 nghìn/tháng", "800k" -> 800000.0
        - "Thỏa thuận", "Liên hệ", "Giá thương lượng" -> "Thỏa thuận" / "Liên hệ" / "Thương lượng"
    """
    if not price_text:
        return None

    text = price_text.strip()
    text_lower = text.lower()

    if any(w in text_lower for w in ["thỏa thuận", "thoa thuan"]):
        return "Thỏa thuận"
    if any(w in text_lower for w in ["thương lượng", "thuong luong", "tl"]):
        return "Thương lượng"
    if any(w in text_lower for w in ["liên hệ", "lien he"]):
        return "Liên hệ"

    # Pattern: "3tr5", "3 triệu 5", "3tr500", "3 tr 5"
    split_trieu = re.search(r"(\d+)\s*(?:triệu|trieu|tr|t)\s*(\d+)", text_lower)
    if split_trieu:
        main_val = float(split_trieu.group(1))
        sub_str = split_trieu.group(2)
        if len(sub_str) == 1:
            sub_val = float(sub_str) / 10.0
        elif len(sub_str) == 2:
            sub_val = float(sub_str) / 100.0
        else:
            sub_val = float(sub_str) / 1000.0
        return round((main_val + sub_val) * 1_000_000)

    # Pattern: 3.5 triệu, 3,5 tr, 3 triệu, 4.1 triệu
    trieu_match = re.search(r"([\d\.,]+)\s*(?:triệu|trieu|tr)", text_lower)
    if trieu_match:
        val_str = trieu_match.group(1).replace(",", ".")
        try:
            return round(float(val_str) * 1_000_000)
        except ValueError:
            pass

    # Pattern: 800 nghìn, 800k, 1750k, 1.750 nghìn
    nghin_match = re.search(r"([\d\.,]+)\s*(?:nghìn|nghin|ngàn|ngan|k)", text_lower)
    if nghin_match:
        raw_str = nghin_match.group(1)
        if "." in raw_str and len(raw_str.split(".")[-1]) == 3:
            # e.g. "1.750" with 3 digits after dot -> thousand separator
            val_str = raw_str.replace(".", "")
        else:
            val_str = raw_str.replace(",", ".")
        try:
            val = float(val_str)
            p_calc = round(val * 1_000)
            if 500 <= p_calc < 10000:
                p_calc = round(p_calc * 1000)
            return p_calc
        except ValueError:
            pass

    # Direct digits: 3500000, 3.500.000, 3500k
    num_match = re.search(r"(\d[\d\.\,]{3,})", text_lower)
    if num_match:
        val_str = num_match.group(1).replace(".", "").replace(",", "")
        try:
            p_calc = round(float(val_str))
            if 500 <= p_calc < 10000:
                p_calc = round(p_calc * 1000)
            return p_calc
        except ValueError:
            pass

    return text if len(text) <= 50 else None


def parse_area(area_text: str) -> Optional[float]:
    """
    Parse area text into float (m2).
    Examples:
        - "25 m²", "25m2", "25 mét vuông" -> 25.0
    """
    if not area_text:
        return None

    text = area_text.lower().strip()
    match = re.search(r"([\d\.,]+)\s*(?:m2|m²|mét vuông)", text)
    if match:
        val_str = match.group(1).replace(",", ".")
        try:
            return round(float(val_str), 2)
        except ValueError:
            return None
    return None


def parse_phongtro123_detail(html_content: str, url: str) -> Dict[str, Any]:
    """
    Parse a single listing detail HTML page from phongtro123.com into canonical dict.
    """
    try:
        soup = BeautifulSoup(html_content, "lxml")
    except Exception:
        soup = BeautifulSoup(html_content, "html.parser")

    # Native ID from URL (e.g., ...-pr654321.html or pr654321)
    native_id_match = re.search(r"-pr(\d+)\.html?", url)
    if not native_id_match:
        native_id_match = re.search(r"pr(\d+)", url)
    if not native_id_match:
        native_id_match = re.search(r"-(\d+)\.html?", url)
    native_id = native_id_match.group(1) if native_id_match else "unknown"

    # Title
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""

    # Price & Area & Time from parent container or header
    parent = h1.parent if h1 else soup
    price_elem = parent.select_one(".text-green.fs-5, .text-green, .item.price, .post-summary .price")
    price_raw = price_elem.get_text(strip=True) if price_elem else ""
    price = parse_price(price_raw)

    area_m2 = None
    for sp in parent.find_all("span"):
        txt = sp.get_text(strip=True)
        if ("m2" in txt or "m²" in txt) and not area_m2:
            area_m2 = parse_area(txt)

    # Address
    address_raw = ""
    addr_elem = soup.select_one(".post-attributes .item.location span, address.post-address, .post-address")
    if addr_elem:
        address_raw = addr_elem.get_text(strip=True)
    if not address_raw:
        for elem in soup.find_all(["div", "p", "address", "li"]):
            t = elem.get_text(" ", strip=True)
            if "Địa chỉ:" in t and len(t) < 300:
                m = re.search(r"Địa chỉ:\s*(.+?)(?:Xem bản đồ|Mã tin|$)", t)
                if m:
                    address_raw = m.group(1).strip()
                    break

    # Description
    description = ""
    for div in soup.find_all(["div", "section"]):
        t = div.get_text("\n", strip=True)
        if t.startswith("Thông tin mô tả"):
            description = t.replace("Thông tin mô tả", "").strip()
            break

    # Posted timestamp / date
    time_tag = soup.select_one("time")
    posted_at_raw = ""
    if time_tag:
        posted_at_raw = time_tag.get("title") or time_tag.get_text(strip=True)

    # Image URLs (up to 8 images, deduplicated)
    images: List[str] = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src and str(src).startswith("http") and not any(logo in str(src) for logo in ["logo", "icon", "banner", "avatar", "default"]):
            if src not in images and not any(src.split("/")[-1] in x for x in images):
                images.append(str(src))
                if len(images) >= 8:
                    break

    # Phone Number (Raw phone number without hashing)
    phone_number = ""
    for a in soup.find_all("a", href=True):
        if a["href"].startswith("tel:"):
            phone_number = a["href"].replace("tel:", "").strip()
            break
    if not phone_number:
        for elem in soup.find_all(["span", "div", "a"]):
            t = elem.get_text(strip=True)
            match = re.search(r"(0\d{9,10})", t)
            if match:
                phone_number = match.group(1)
                break

    rec = {
        "listing_id": f"phongtro123_{native_id}",
        "source": "phongtro123",
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
