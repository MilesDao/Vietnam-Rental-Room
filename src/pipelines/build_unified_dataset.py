#!/usr/bin/env python3
"""
Unified Dataset Builder for Hanoi Rental Listings.
Normalizes listings from YourHome.top, Rencity.vn, and PhongTot.com into a standardized schema:
  - district, address, price, house_type, electric_price, water_price, wifi_price, other_utilities_price
  - Additional features: area_m2, parking_fee, amenities (AC, heater, fridge, washer, elevator, balcony, fire safety),
    GPS coordinates, contact info, image links, platform source, etc.
"""

import csv
import json
import math
import os
import re
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from typing import Any, Dict, List, Optional, Tuple

DISTRICT_MAP = {
    "cau-giay": "Cầu Giấy",
    "cầu giấy": "Cầu Giấy",
    "cau giay": "Cầu Giấy",
    "nam-tu-liem": "Nam Từ Liêm",
    "nam từ liêm": "Nam Từ Liêm",
    "nam tu liem": "Nam Từ Liêm",
    "dong-da": "Đống Đa",
    "đống đa": "Đống Đa",
    "dong da": "Đống Đa",
    "ba-dinh": "Ba Đình",
    "ba đình": "Ba Đình",
    "ba dinh": "Ba Đình",
    "thanh-xuan": "Thanh Xuân",
    "thanh xuân": "Thanh Xuân",
    "thanh xuan": "Thanh Xuân",
    "tay-ho": "Tây Hồ",
    "tây hồ": "Tây Hồ",
    "tay ho": "Tây Hồ",
    "hoang-mai": "Hoàng Mai",
    "hoàng mai": "Hoàng Mai",
    "hoang mai": "Hoàng Mai",
    "bac-tu-liem": "Bắc Từ Liêm",
    "bắc từ liêm": "Bắc Từ Liêm",
    "bac tu liem": "Bắc Từ Liêm",
    "hai-ba-trung": "Hai Bà Trưng",
    "hai bà trưng": "Hai Bà Trưng",
    "hai ba trung": "Hai Bà Trưng",
    "ha-dong": "Hà Đông",
    "hà đông": "Hà Đông",
    "ha dong": "Hà Đông",
    "hoan-kiem": "Hoàn Kiếm",
    "hoàn kiếm": "Hoàn Kiếm",
    "hoan kiem": "Hoàn Kiếm",
    "long-bien": "Long Biên",
    "long biên": "Long Biên",
    "long bien": "Long Biên",
    "thanh-tri": "Thanh Trì",
    "thanh trì": "Thanh Trì",
    "thanh tri": "Thanh Trì",
    "gia-lam": "Gia Lâm",
    "gia lâm": "Gia Lâm",
    "dong-anh": "Đông Anh",
    "đông anh": "Đông Anh",
    "hoai-duc": "Hoài Đức",
    "hoài đức": "Hoài Đức",
}

WARD_TO_DISTRICT = {
    "Dịch Vọng": "Cầu Giấy",
    "Dịch Vọng Hậu": "Cầu Giấy",
    "Mai Dịch": "Cầu Giấy",
    "Nghĩa Đô": "Cầu Giấy",
    "Nghĩa Tân": "Cầu Giấy",
    "Quan Hoa": "Cầu Giấy",
    "Trung Hòa": "Cầu Giấy",
    "Yên Hòa": "Cầu Giấy",
    "Cầu Giấy": "Cầu Giấy",
    "Mỹ Đình 1": "Nam Từ Liêm",
    "Mỹ Đình 2": "Nam Từ Liêm",
    "Mễ Trì": "Nam Từ Liêm",
    "Phú Đô": "Nam Từ Liêm",
    "Trung Văn": "Nam Từ Liêm",
    "Tây Mỗ": "Nam Từ Liêm",
    "Đại Mỗ": "Nam Từ Liêm",
    "Phương Canh": "Nam Từ Liêm",
    "Xuân Phương": "Nam Từ Liêm",
    "Cầu Diễn": "Nam Từ Liêm",
    "Cống Vị": "Ba Đình",
    "Điện Biên": "Ba Đình",
    "Đội Cấn": "Ba Đình",
    "Giảng Võ": "Ba Đình",
    "Kim Mã": "Ba Đình",
    "Liễu Giai": "Ba Đình",
    "Ngọc Hà": "Ba Đình",
    "Ngọc Khánh": "Ba Đình",
    "Nguyễn Trung Trực": "Ba Đình",
    "Phúc Xá": "Ba Đình",
    "Quán Thánh": "Ba Đình",
    "Thành Công": "Ba Đình",
    "Trúc Bạch": "Ba Đình",
    "Vĩnh Phúc": "Ba Đình",
    "Cát Linh": "Đống Đa",
    "Hàng Bột": "Đống Đa",
    "Khâm Thiên": "Đống Đa",
    "Khương Thượng": "Đống Đa",
    "Kim Liên": "Đống Đa",
    "Láng Hạ": "Đống Đa",
    "Láng Thượng": "Đống Đa",
    "Nam Đồng": "Đống Đa",
    "Ngã Tư Sở": "Đống Đa",
    "Ô Chợ Dừa": "Đống Đa",
    "Phương Liên": "Đống Đa",
    "Phương Mai": "Đống Đa",
    "Quang Trung": "Đống Đa",
    "Quốc Tử Giám": "Đống Đa",
    "Thịnh Quang": "Đống Đa",
    "Thổ Quan": "Đống Đa",
    "Trung Liệt": "Đống Đa",
    "Trung Phụng": "Đống Đa",
    "Trung Tự": "Đống Đa",
    "Văn Chương": "Đống Đa",
    "Văn Miếu": "Đống Đa",
    "Hạ Đình": "Thanh Xuân",
    "Khương Đình": "Thanh Xuân",
    "Khương Mai": "Thanh Xuân",
    "Khương Trung": "Thanh Xuân",
    "Kim Giang": "Thanh Xuân",
    "Phương Liệt": "Thanh Xuân",
    "Thanh Xuân Bắc": "Thanh Xuân",
    "Thanh Xuân Nam": "Thanh Xuân",
    "Thanh Xuân Trung": "Thanh Xuân",
    "Thượng Đình": "Thanh Xuân",
    "Nhân Chính": "Thanh Xuân",
    "Bưởi": "Tây Hồ",
    "Nhật Tân": "Tây Hồ",
    "Phú Thượng": "Tây Hồ",
    "Quảng An": "Tây Hồ",
    "Thụy Khuê": "Tây Hồ",
    "Tứ Liên": "Tây Hồ",
    "Xuân La": "Tây Hồ",
    "Yên Phụ": "Tây Hồ",
    "Đại Kim": "Hoàng Mai",
    "Định Công": "Hoàng Mai",
    "Giáp Bát": "Hoàng Mai",
    "Hoàng Liệt": "Hoàng Mai",
    "Hoàng Văn Thụ": "Hoàng Mai",
    "Lĩnh Nam": "Hoàng Mai",
    "Mai Động": "Hoàng Mai",
    "Tân Mai": "Hoàng Mai",
    "Thanh Trì": "Hoàng Mai",
    "Thịnh Liệt": "Hoàng Mai",
    "Trần Phú": "Hoàng Mai",
    "Tương Mai": "Hoàng Mai",
    "Vĩnh Hưng": "Hoàng Mai",
    "Yên Sở": "Hoàng Mai",
    "Cổ Nhuế 1": "Bắc Từ Liêm",
    "Cổ Nhuế 2": "Bắc Từ Liêm",
    "Đông Ngạc": "Bắc Từ Liêm",
    "Đức Thắng": "Bắc Từ Liêm",
    "Liên Mạc": "Bắc Từ Liêm",
    "Minh Khai": "Bắc Từ Liêm",
    "Phú Diễn": "Bắc Từ Liêm",
    "Phúc Diễn": "Bắc Từ Liêm",
    "Tây Tựu": "Bắc Từ Liêm",
    "Thượng Cát": "Bắc Từ Liêm",
    "Thụy Phương": "Bắc Từ Liêm",
    "Xuân Đỉnh": "Bắc Từ Liêm",
    "Xuân Tảo": "Bắc Từ Liêm",
    "Bạch Đằng": "Hai Bà Trưng",
    "Bách Khoa": "Hai Bà Trưng",
    "Bạch Mai": "Hai Bà Trưng",
    "Cầu Dền": "Hai Bà Trưng",
    "Đống Mác": "Hai Bà Trưng",
    "Đồng Nhân": "Hai Bà Trưng",
    "Đồng Tâm": "Hai Bà Trưng",
    "Lê Đại Hành": "Hai Bà Trưng",
    "Minh Khai": "Hai Bà Trưng",
    "Nguyễn Du": "Hai Bà Trưng",
    "Phạm Đình Hổ": "Hai Bà Trưng",
    "Phố Huế": "Hai Bà Trưng",
    "Quỳnh Lôi": "Hai Bà Trưng",
    "Quỳnh Mai": "Hai Bà Trưng",
    "Thanh Lương": "Hai Bà Trưng",
    "Thanh Nhàn": "Hai Bà Trưng",
    "Trương Định": "Hai Bà Trưng",
    "Vĩnh Tuy": "Hai Bà Trưng",
    "Biên Giang": "Hà Đông",
    "Đồng Mai": "Hà Đông",
    "Dương Nội": "Hà Đông",
    "Hà Cầu": "Hà Đông",
    "Kiến Hưng": "Hà Đông",
    "La Khê": "Hà Đông",
    "Mộ Lao": "Hà Đông",
    "Nguyễn Trãi": "Hà Đông",
    "Phú La": "Hà Đông",
    "Phú Lãm": "Hà Đông",
    "Phú Lương": "Hà Đông",
    "Phúc La": "Hà Đông",
    "Quang Trung": "Hà Đông",
    "Vạn Phúc": "Hà Đông",
    "Văn Quán": "Hà Đông",
    "Yên Nghĩa": "Hà Đông",
    "Yết Kiêu": "Hà Đông",
}


def normalize_district(raw_district: str, address_or_ward: str = "") -> str:
    """Normalize district name using raw string or context from address/ward."""
    d_clean = (raw_district or "").strip().lower()
    for key, canonical in DISTRICT_MAP.items():
        if key in d_clean:
            return canonical

    # Try detecting from ward / address
    aw = address_or_ward or ""
    for ward, canonical in WARD_TO_DISTRICT.items():
        if ward.lower() in aw.lower():
            return canonical

    for key, canonical in DISTRICT_MAP.items():
        if key in aw.lower():
            return canonical

    return raw_district.strip() or "Chưa rõ"


def normalize_house_type(type_code: str, title: str = "", desc: str = "") -> str:
    """Map type keywords to clean human-readable Vietnamese house type."""
    combined = f"{type_code} {title} {desc}".lower()

    if re.search(r'\b(?:1-ngu|1pn|1n1k|1 phòng ngủ|1 ngủ)\b', combined):
        return "1 Phòng Ngủ (1PN/1N1K)"
    elif re.search(r'\b(?:2-ngu|2pn|2n1k|2 phòng ngủ|2 ngủ)\b', combined):
        return "2 Phòng Ngủ (2PN/2N1K)"
    elif re.search(r'\b(?:gacxep|gác xép|gác lửng|duplex)\b', combined):
        return "Gác xép / Duplex"
    elif re.search(r'\b(?:wc-chung|chung wc|wc chung)\b', combined):
        return "Phòng trọ WC chung"
    elif re.search(r'\b(?:nguyen-can|nguyên căn|nhà riêng)\b', combined):
        return "Nhà nguyên căn"
    elif re.search(r'\b(?:ccmn|chung cư mini)\b', combined):
        return "Chung cư mini (CCMN)"
    elif re.search(r'\b(?:studio|khép kín)\b', combined):
        return "Studio khép kín"
    elif "căn hộ" in combined:
        return "Căn hộ dịch vụ"
    elif "phòng trọ" in combined or "nhà trọ" in combined:
        return "Phòng trọ"
    elif "tòa" in combined or "renhouse" in combined:
        return "Tòa nhà căn hộ / Phòng trọ"
    return "Phòng trọ / Căn hộ"


def parse_utilities(raw_text_or_list: Any) -> Dict[str, str]:
    """Parse electric, water, wifi, parking, and other utilities from array or text."""
    if not raw_text_or_list:
        return {
            "electric_price": "",
            "water_price": "",
            "wifi_price": "",
            "other_utilities_price": "",
            "parking_fee": "",
        }

    if isinstance(raw_text_or_list, list):
        full_text = "\n".join(str(x) for x in raw_text_or_list)
    else:
        full_text = str(raw_text_or_list)

    clauses = re.split(r'[\n\r;•\*]+|(?:\s*-\s*)', full_text)
    expanded = []
    for c in clauses:
        sub = re.split(
            r',\s*(?=(?:[Đđ]iện|[Nn]ước|[Ww]ifi|[Mm]ạng|[Ii]nternet|[Dd]vc|[Dd]ịch vụ|[Pp]hí|[Gg]ửi xe|[Xx]e|[Tt]hang máy|[Vv]ệ sinh|[Rr]ác)\b)',
            c
        )
        expanded.extend(sub)

    elec = ""
    water = ""
    wifi = ""
    parking = ""
    others = []

    # Check for blanket "điện nước giá dân"
    if re.search(r'điện\s*nước\s*giá\s*dân', full_text, re.IGNORECASE):
        elec = "Điện nước giá dân"
        water = "Điện nước giá dân"

    for clause in expanded:
        c = clause.strip()
        if not c:
            continue

        # Electric
        if re.search(r'^[Đđ]iện\b|^Số điện\b', c, re.IGNORECASE) and not elec:
            val = re.sub(r'^[Đđ]iện[\s:]*|^Số điện[\s:]*', '', c).strip()
            elec = val or "Theo công tơ"
        elif "giá dân" in c.lower() and not elec:
            elec = "Giá dân"

        # Water
        if re.search(r'^[Nn]ước\b', c, re.IGNORECASE) and not water:
            val = re.sub(r'^[Nn]ước[\s:]*', '', c).strip()
            water = val or "Theo quy định"

        # Wifi
        if re.search(r'^(?:[Ww]ifi|[Mm]ạng|[Ii]nternet)\b', c, re.IGNORECASE) and not wifi:
            val = re.sub(r'^(?:[Ww]ifi|[Mm]ạng|[Ii]nternet)[\s:]*', '', c).strip()
            wifi = val or "Có sẵn"

        # Parking
        if re.search(r'^(?:[Gg]ửi xe|[Đđ]ể xe|[Pp]hí xe|[Xx]e máy|[Xx]e)\b', c, re.IGNORECASE) and not parking:
            val = re.sub(r'^(?:[Gg]ửi xe|[Đđ]ể xe|[Pp]hí xe|[Xx]e máy|[Xx]e)[\s:]*', '', c).strip()
            parking = val or "Có chỗ để xe"

        # Other utilities
        if re.search(r'^(?:[Dd]vc|[Dd]ịch vụ|[Pp]hí dịch vụ|[Tt]hang máy|[Vv]ệ sinh|[Rr]ác|[Mm]áy giặt|[Mm]áy sấy)\b', c, re.IGNORECASE):
            if c not in others and len(c) < 60:
                others.append(c)

    return {
        "electric_price": elec,
        "water_price": water,
        "wifi_price": wifi,
        "other_utilities_price": "; ".join(others),
        "parking_fee": parking,
    }


def parse_amenities_flags(text_or_list: Any) -> Dict[str, bool]:
    """Detect boolean flags for common amenities."""
    combined = " ".join(text_or_list) if isinstance(text_or_list, list) else str(text_or_list or "")
    c = combined.lower()

    return {
        "air_conditioner": bool(re.search(r'điều hòa|máy lạnh|đh\b', c)),
        "water_heater": bool(re.search(r'nóng lạnh|bình nóng lạnh|nl\b', c)),
        "refrigerator": bool(re.search(r'tủ lạnh|tl\b', c)),
        "washing_machine": bool(re.search(r'máy giặt|giặt chung|mg\b', c)),
        "elevator": bool(re.search(r'thang máy|tm\b', c)),
        "balcony_window": bool(re.search(r'ban công|cửa sổ|giếng trời', c)),
        "pet_allowed": bool(re.search(r'cho nuôi pet|nuôi pet|pet\b|thú cưng', c)),
    }


def process_yourhome(filepath: str) -> List[Dict[str, Any]]:
    print(f"Processing YourHome listings from {filepath}...")
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    unified = []
    for item in data:
        contact = item.get("contact") or {}
        utilities = parse_utilities(item.get("utilityCosts") or [])
        amenities = item.get("amenities") or []
        desc = item.get("description") or ""
        title = item.get("title") or ""
        restrictions = item.get("restrictions") or []

        # Whole house check: in Vietnam, whole houses pay direct residential utility rates
        is_whole_house = "nguyên căn" in (item.get("roomType", "") + " " + title + " " + desc).lower()
        if is_whole_house:
            if not utilities["electric_price"]:
                utilities["electric_price"] = "Điện nước giá dân"
            if not utilities["water_price"]:
                utilities["water_price"] = "Điện nước giá dân"
            if not utilities["other_utilities_price"]:
                utilities["other_utilities_price"] = "Tự chi trả theo hóa đơn thực tế"

        if not utilities["wifi_price"]:
            if any("wifi" in a.lower() or "mạng" in a.lower() for a in amenities):
                utilities["wifi_price"] = "Có sẵn (Miễn phí)"

        # Parking from restrictions if not in utilities
        parking = utilities["parking_fee"]
        if not parking:
            for r in restrictions:
                if "xe" in r.lower():
                    parking = r
                    break
        if not parking and is_whole_house:
            parking = "Có chỗ để xe trong nhà"

        flags = parse_amenities_flags(amenities + [desc, title])
        district = normalize_district(item.get("district", ""), title)
        house_type = normalize_house_type(item.get("roomType", ""), title, desc)

        images = [img for img in (item.get("images") or []) if img and img.strip()]

        unified.append({
            "platform": "YourHome.top",
            "listing_id": f"YH_{item.get('id')}",
            "title": title.strip(),
            "district": district,
            "ward": "",
            "address": title.strip(),
            "price_vnd": item.get("price") or 0,
            "house_type": house_type,
            "area_m2": item.get("area") or "",
            "electric_price": utilities["electric_price"],
            "water_price": utilities["water_price"],
            "wifi_price": utilities["wifi_price"],
            "other_utilities_price": utilities["other_utilities_price"],
            "parking_fee": parking,
            **flags,
            "amenities_list": "; ".join(amenities),
            "latitude": item.get("lat") or "",
            "longitude": item.get("lng") or "",
            "contact_name": contact.get("name", "").strip(),
            "contact_phone": contact.get("phone", "").strip(),
            "contact_zalo": contact.get("zalo", "").strip(),
            "image_count": len(images),
            "image_urls": " | ".join(images),
            "listing_url": f"https://yourhome.top/?city=ha-noi",
        })

    print(f"  -> Processed {len(unified)} YourHome listings.")
    return unified


def fetch_rencity_details_batch(posts: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    # Check if scratch cache exists
    cache_path = "/home/totallynotminh/.gemini/antigravity-cli/brain/00b2f06e-a982-4ccd-ab9e-d2f7e335101a/scratch/rencity_details.json"
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                cached = json.load(f)
            if len(cached) >= len(posts) * 0.9:
                print(f"Loaded {len(cached)} Rencity post details from cache.")
                return {int(k): v for k, v in cached.items()}
        except Exception:
            pass

    print(f"Fetching full descriptions and motel details for {len(posts)} Rencity posts concurrently...")
    base = "https://api1.renapp.vn/api/user/community/mo_posts"
    headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
    details_map = {}

    def fetch_one(pid):
        req = urllib.request.Request(f"{base}/{pid}", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                d = json.loads(resp.read().decode("utf-8")).get("data", {})
                return pid, d
        except Exception:
            return pid, None

    with ThreadPoolExecutor(max_workers=30) as executor:
        results = executor.map(fetch_one, [p["id"] for p in posts])
        for pid, d in results:
            if d:
                details_map[pid] = d

    print(f"  -> Successfully enriched {len(details_map)}/{len(posts)} Rencity post details.")
    return details_map


def process_rencity(filepath: str) -> List[Dict[str, Any]]:
    print(f"Processing Rencity listings from {filepath}...")
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    details_map = fetch_rencity_details_batch(data)

    unified = []
    dropped_count = 0
    for item in data:
        pid = item.get("id")
        detail = details_map.get(pid, {})
        if not detail:
            dropped_count += 1
            continue

        motels = detail.get("motel") or []
        desc = detail.get("description") or ""
        title = item.get("title") or ""
        user = detail.get("user") or {}

        # 1. Area: from motel units (min - max if varied)
        areas = [m["area"] for m in motels if isinstance(m.get("area"), (int, float)) and m["area"] > 0]
        if areas:
            min_a, max_a = int(min(areas)), int(max(areas))
            area_str = f"{min_a}" if min_a == max_a else f"{min_a} - {max_a}"
        elif item.get("area") and item.get("area") > 0:
            area_str = str(int(item["area"]))
        else:
            m_a = re.search(r'(\d+)\s*(?:m2|m²)', desc)
            area_str = m_a.group(1) if m_a else ""

        # 2. Services / Utilities from motel mo_services
        all_services = []
        for m in motels:
            for s in m.get("mo_services") or []:
                name = (s.get("service_name") or "").strip()
                charge = s.get("service_charge")
                unit = (s.get("service_unit") or "").strip()
                if name and charge is not None:
                    all_services.append((name, charge, unit))

        seen_s = set()
        dedup_s = []
        for n, c, u in all_services:
            k = (n.lower(), c, u.lower())
            if k not in seen_s:
                seen_s.add(k)
                dedup_s.append((n, c, u))

        elec_list, water_list, wifi_list, parking_list, other_dict = [], [], [], [], {}
        for n, c, u in dedup_s:
            nl = n.lower()
            if re.search(r'^[đd]iện\b', nl):
                elec_list.append((c, u or "Kwh"))
            elif re.search(r'^[n]ước\b', nl):
                u_clean = "người" if "người" in u.lower() else (u or "m3")
                water_list.append((c, u_clean))
            elif re.search(r'^(?:mạng|wifi|internet)\b', nl):
                u_clean = "phòng" if "phòng" in u.lower() else (u or "phòng")
                wifi_list.append((c, u_clean))
            elif re.search(r'(?:gửi xe|trông xe|xe máy|xe điện|xe\b)', nl):
                u_clean = "người" if "người" in u.lower() else (u or "xe")
                parking_list.append(f"{n}: {c:,}đ/{u_clean}".replace(",", "."))
            else:
                u_clean = f"/{u}" if u and len(u) < 15 and u.lower() not in ("vnd", "đ") else ""
                if "người" in u.lower():
                    u_clean = "/người"
                if n not in other_dict:
                    other_dict[n] = []
                other_dict[n].append((c, u_clean))

        # Format electric
        if elec_list:
            charges = [c for c, u in elec_list if c > 0]
            units = list(dict.fromkeys(u for c, u in elec_list))
            u_str = units[0] if units else "Kwh"
            if charges:
                min_c, max_c = min(charges), max(charges)
                elec_str = f"{min_c:,}đ/{u_str}".replace(",", ".") if min_c == max_c else f"{min_c:,} - {max_c:,}đ/{u_str}".replace(",", ".")
            else:
                elec_str = "Miễn phí"
        else:
            txt_u = parse_utilities(desc)
            elec_str = txt_u["electric_price"]

        # Format water
        if water_list:
            charges = [c for c, u in water_list if c > 0]
            units = list(dict.fromkeys(u for c, u in water_list))
            u_str = units[0] if units else "m3"
            if charges:
                min_c, max_c = min(charges), max(charges)
                water_str = f"{min_c:,}đ/{u_str}".replace(",", ".") if min_c == max_c else f"{min_c:,} - {max_c:,}đ/{u_str}".replace(",", ".")
            else:
                water_str = "Miễn phí"
        else:
            txt_u = parse_utilities(desc)
            water_str = txt_u["water_price"]

        # Format wifi
        if wifi_list:
            charges = [c for c, u in wifi_list if c > 0]
            units = list(dict.fromkeys(u for c, u in wifi_list))
            u_str = units[0] if units else "phòng"
            if charges:
                min_c, max_c = min(charges), max(charges)
                wifi_str = f"{min_c:,}đ/{u_str}".replace(",", ".") if min_c == max_c else f"{min_c:,} - {max_c:,}đ/{u_str}".replace(",", ".")
            else:
                wifi_str = "Miễn phí"
        else:
            wifi_str = ""
            for m in motels:
                wm = m.get("wifi_money")
                hw = m.get("has_wifi")
                if wm and wm > 0:
                    wifi_str = f"{wm:,}đ/phòng".replace(",", ".")
                    break
                elif hw is True:
                    wifi_str = "Có sẵn (Miễn phí)"
                    break
            if not wifi_str:
                txt_u = parse_utilities(desc)
                wifi_str = txt_u["wifi_price"]

        # Format parking
        if parking_list:
            parking_str = "; ".join(dict.fromkeys(parking_list))
        else:
            parking_str = ""
            for m in motels:
                pm = m.get("park_money")
                hp = m.get("has_park")
                if pm and pm > 0:
                    parking_str = f"{pm:,}đ/xe".replace(",", ".")
                    break
                elif hp is True:
                    parking_str = "Có chỗ để xe (Miễn phí)"
                    break
            if not parking_str:
                txt_u = parse_utilities(desc)
                parking_str = txt_u["parking_fee"]

        # Format others
        other_formatted = []
        for n, items in other_dict.items():
            charges = [c for c, u in items]
            units = [u for c, u in items]
            u_str = units[0] if units else ""
            if len(charges) == 1:
                other_formatted.append(f"{n}: {charges[0]:,}đ{u_str}".replace(",", "."))
            else:
                min_c, max_c = min(charges), max(charges)
                val_str = f"{min_c:,}đ{u_str}".replace(",", ".") if min_c == max_c else f"{min_c:,} - {max_c:,}đ{u_str}".replace(",", ".")
                other_formatted.append(f"{n}: {val_str}")
        if other_formatted:
            other_str = "; ".join(other_formatted)
        else:
            txt_u = parse_utilities(desc)
            other_str = txt_u["other_utilities_price"]

        # Booleans
        has_ac = any(m.get("has_air_conditioner") for m in motels) or bool(re.search(r'điều hòa|máy lạnh|đh\b', desc, re.I))
        has_wh = any(m.get("has_water_heater") for m in motels) or bool(re.search(r'nóng lạnh|bình nóng lạnh|nl\b', desc, re.I))
        has_ref = any(m.get("has_fridge") for m in motels) or bool(re.search(r'tủ lạnh|tl\b', desc, re.I))
        has_wm = any(m.get("has_washing_machine") for m in motels) or any("máy giặt" in n.lower() for n, c, u in dedup_s) or bool(re.search(r'máy giặt|giặt chung', desc, re.I))
        has_ele = any("thang máy" in n.lower() for n, c, u in dedup_s) or bool(re.search(r'thang máy|tm\b', f"{title} {desc}", re.I))
        has_bw = any(m.get("has_balcony") or m.get("has_window") for m in motels) or bool(re.search(r'ban công|cửa sổ|giếng trời', desc, re.I))
        has_fire = any("pccc" in n.lower() or "chữa cháy" in n.lower() for n, c, u in dedup_s) or bool(re.search(r'pccc|bình chữa cháy|chữa cháy|thoát hiểm', desc, re.I))
        has_pet = any(m.get("has_pet") for m in motels) or bool(re.search(r'cho nuôi pet|nuôi pet|thú cưng', desc, re.I))

        # Amenities list
        amenities = []
        if has_ac: amenities.append("Điều hòa")
        if has_wh: amenities.append("Nóng lạnh")
        if has_ref: amenities.append("Tủ lạnh")
        if has_wm: amenities.append("Máy giặt")
        if any(m.get("has_bed") for m in motels): amenities.append("Giường")
        if any(m.get("has_wardrobe") for m in motels): amenities.append("Tủ quần áo")
        if any(m.get("has_kitchen") for m in motels): amenities.append("Kệ bếp")
        if any(m.get("has_mezzanine") for m in motels): amenities.append("Gác xép")
        if any(m.get("has_balcony") for m in motels): amenities.append("Ban công")
        if any(m.get("has_window") for m in motels): amenities.append("Cửa sổ")
        if any(m.get("has_wc") for m in motels): amenities.append("WC riêng")
        if any(m.get("has_finger_print") for m in motels): amenities.append("Khóa vân tay")
        if any(m.get("has_free_move") for m in motels): amenities.append("Giờ giấc tự do")
        if any(m.get("has_own_owner") for m in motels): amenities.append("Không chung chủ")
        if any(m.get("has_security") for m in motels): amenities.append("An ninh / Bảo vệ")
        if has_ele: amenities.append("Thang máy")
        if has_fire: amenities.append("PCCC")
        if has_pet: amenities.append("Cho nuôi thú cưng")
        if parking_str: amenities.append("Chỗ để xe")
        if any(m.get("has_table") for m in motels): amenities.append("Bàn ghế")
        if any(m.get("has_sofa") for m in motels): amenities.append("Sofa")
        if any(m.get("has_tivi") for m in motels): amenities.append("Tivi")
        if any(m.get("has_ceiling_fans") for m in motels): amenities.append("Quạt trần")
        if any(m.get("has_curtain") for m in motels): amenities.append("Rèm cửa")

        furnitures = detail.get("furniture") or []
        for f in furnitures:
            if isinstance(f, dict) and f.get("name") and f["name"] not in amenities:
                amenities.append(f["name"])

        ward = (item.get("wards_name") or "").replace("Phường ", "").replace("Xã ", "").strip()
        address = item.get("address_detail") or ""
        district = normalize_district("", f"{ward} {address}")

        price = item.get("min_money") or item.get("max_money") or 0
        house_type = normalize_house_type(str(item.get("type", "")), title, desc)

        phone = user.get("phone_number") or (motels[0].get("phone_number") if motels else "") or ""
        contact_name = user.get("name") or (detail.get("host") or {}).get("name") or "Chủ nhà"
        lat = detail.get("lat") or (motels[0].get("lat") if motels else "") or item.get("lat") or ""
        lng = detail.get("lng") or (motels[0].get("lng") if motels else "") or item.get("lng") or ""

        images = [img for img in (item.get("images") or detail.get("images") or (motels[0].get("images") if motels else []) or []) if img and img.strip()]

        unified.append({
            "platform": "Rencity.vn",
            "listing_id": f"RC_{pid}",
            "title": title.strip(),
            "district": district,
            "ward": ward,
            "address": address.strip(),
            "price_vnd": price,
            "house_type": house_type,
            "area_m2": area_str,
            "electric_price": elec_str,
            "water_price": water_str,
            "wifi_price": wifi_str,
            "other_utilities_price": other_str,
            "parking_fee": parking_str,
            "air_conditioner": has_ac,
            "water_heater": has_wh,
            "refrigerator": has_ref,
            "washing_machine": has_wm,
            "elevator": has_ele,
            "balcony_window": has_bw,
            "pet_allowed": has_pet,
            "amenities_list": "; ".join(amenities),
            "latitude": lat,
            "longitude": lng,
            "contact_name": contact_name,
            "contact_phone": phone,
            "contact_zalo": phone,
            "image_count": len(images),
            "image_urls": " | ".join(images),
            "listing_url": f"https://rencity.vn/search?post_id={pid}",
        })

    print(f"  -> Processed {len(unified)} Rencity listings (dropped {dropped_count} deleted/missing listings).")
    return unified


def fetch_phongtot_details_batch(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    # Check if scratch cache exists
    cache_path = "/home/totallynotminh/.gemini/antigravity-cli/brain/00b2f06e-a982-4ccd-ab9e-d2f7e335101a/scratch/phongtot_details.json"
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                cached = json.load(f)
            if len(cached) >= len(items) * 0.9:
                print(f"Loaded {len(cached)} PhongTot detail pages from cache.")
                return cached
        except Exception:
            pass

    print(f"Fetching full SSR pages for {len(items)} PhongTot listings concurrently...")
    headers = {"User-Agent": "Mozilla/5.0"}
    details_map = {}

    def fetch_pt(it):
        url = it.get("url")
        if not url:
            return url, None
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                html = unescape(raw)
                coords = re.findall(r'maps\.google\.com/maps\?q=([0-9\.]+),([0-9\.]+)', html)
                lat, lng = coords[0] if coords else ("", "")
                elec = re.findall(r'Tiền điện[\s\S]*?([\d\.]+\s*đ/[^<\n\r]+)', html)
                water = re.findall(r'Tiền nước[\s\S]*?([\d\.]+\s*đ/[^<\n\r]+)', html)
                other = re.findall(r'Dịch vụ khác[\s\S]*?([\d\.]+\s*đ/[^<\n\r]+)', html)

                sec2 = re.search(r'section-2[\s\S]*?(?:section-3|$)', html)
                amenities = []
                if sec2:
                    text = re.sub(r'<[^>]+>', '\n', sec2.group(0))
                    for l in text.splitlines():
                        ls = l.strip().replace("(*)", "").strip()
                        if ls and "section" not in ls and "Tiện ích" not in ls and len(ls) < 40:
                            if ls not in amenities:
                                amenities.append(ls)

                sec6 = re.search(r'section-6[\s\S]*?(?:section-|$)', html)
                sec6_text = sec6.group(0) if sec6 else ""
                pet = "Nuôi thú cưng" in sec6_text and "Không nuôi thú cưng" not in sec6_text

                return url, {
                    "url": url,
                    "lat": lat,
                    "lng": lng,
                    "elec": elec[0].strip() if elec else "",
                    "water": water[0].strip() if water else "",
                    "other": other[0].strip() if other else "",
                    "amenities": amenities,
                    "pet": pet,
                }
        except Exception:
            return url, None

    with ThreadPoolExecutor(max_workers=35) as executor:
        for url, d in executor.map(fetch_pt, items):
            if d:
                details_map[url] = d

    print(f"  -> Successfully enriched {len(details_map)}/{len(items)} PhongTot detail pages.")
    return details_map


def process_phongtot(filepath: str) -> List[Dict[str, Any]]:
    print(f"Processing PhongTot listings from {filepath}...")
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    pt_details = fetch_phongtot_details_batch(data)

    unified = []
    for item in data:
        url = item.get("url", "")
        pt_d = pt_details.get(url, {})

        base_amenities = item.get("amenities") or []
        detail_amenities = pt_d.get("amenities") or []
        combined_amenities = list(dict.fromkeys(base_amenities + detail_amenities))
        amenities_text = " ".join(combined_amenities + [item.get("title", ""), item.get("address", "")]).lower()

        flags = parse_amenities_flags(combined_amenities + [item.get("title", ""), item.get("address", "")])
        if pt_d.get("pet") is True:
            flags["pet_allowed"] = True
        if any("thang máy" in a.lower() for a in combined_amenities):
            flags["elevator"] = True
        if any("giặt" in a.lower() for a in combined_amenities):
            flags["washing_machine"] = True

        district = normalize_district(item.get("district", ""), item.get("address", ""))
        house_type = normalize_house_type("", item.get("title", ""))

        price = int(item.get("min_price_vnd")) if item.get("min_price_vnd") and str(item.get("min_price_vnd")).isdigit() else 0
        area = item.get("area", "").replace("m2", "").strip()

        # Parking
        if "Ô tô đỗ cửa" in combined_amenities:
            parking = "Ô tô đỗ cửa, khu để xe máy"
        elif any("khu để xe" in a.lower() or "xe" in a.lower() for a in combined_amenities):
            parking = "Khu để xe máy / Có chỗ để xe"
        else:
            parking = "Có chỗ để xe máy"

        # Utilities
        elec = pt_d.get("elec") or "Công tơ riêng / Giá dân"
        water = pt_d.get("water") or "Công tơ riêng / Giá dân"
        wifi = "Có sẵn (theo tòa)"
        other = pt_d.get("other") or "Phí dịch vụ tòa nhà"

        lat = pt_d.get("lat") or ""
        lng = pt_d.get("lng") or ""

        images = [img for img in (item.get("images") or []) if img and img.strip()]

        unified.append({
            "platform": "PhongTot.com",
            "listing_id": f"PT_{item.get('id')}",
            "title": item.get("title", "").strip(),
            "district": district,
            "ward": "",
            "address": item.get("address", "").strip(),
            "price_vnd": price,
            "house_type": house_type,
            "area_m2": area,
            "electric_price": elec,
            "water_price": water,
            "wifi_price": wifi,
            "other_utilities_price": other,
            "parking_fee": parking,
            **flags,
            "amenities_list": "; ".join(combined_amenities),
            "latitude": lat,
            "longitude": lng,
            "contact_name": "Phòng Tốt",
            "contact_phone": "0888022821",
            "contact_zalo": "0888022821",
            "image_count": item.get("image_count") or len(images),
            "image_urls": " | ".join(images),
            "listing_url": url,
        })

    print(f"  -> Processed {len(unified)} PhongTot listings.")
    return unified


UNIFIED_HEADERS = [
    "platform", "listing_id", "title", "district", "ward", "address",
    "price_vnd", "house_type", "area_m2", "electric_price", "water_price",
    "wifi_price", "other_utilities_price", "parking_fee",
    "air_conditioner", "water_heater", "refrigerator", "washing_machine",
    "elevator", "balcony_window", "pet_allowed",
    "amenities_list", "latitude", "longitude",
    "contact_phone", "image_count", "image_urls",
    "listing_url"
]


def save_unified_csv(items: List[Dict[str, Any]], filepath: str) -> None:
    if not items:
        return
    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=UNIFIED_HEADERS)
        writer.writeheader()
        for it in items:
            writer.writerow({k: it.get(k, "") for k in UNIFIED_HEADERS})
    print(f"\nSaved {len(items)} unified listings to CSV: {filepath}")


def save_unified_json(items: List[Dict[str, Any]], filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(items)} unified listings to JSON: {filepath}")


def print_overall_summary(items: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 60)
    print(f"UNIFIED HANOI RENTAL DATASET: Total {len(items):,} listings")
    print("=" * 60)

    by_platform = Counter(i["platform"] for i in items)
    by_district = Counter(i["district"] for i in items)
    by_house_type = Counter(i["house_type"] for i in items)

    print("\nListing Count by Platform:")
    for p, c in by_platform.items():
        print(f"  - {p:15}: {c:,} listings")

    print("\nTop 10 Districts:")
    for d, c in by_district.most_common(10):
        print(f"  - {d:15}: {c:,} listings")

    print("\nListing Count by House Type:")
    for ht, c in by_house_type.most_common():
        print(f"  - {ht:30}: {c:,} listings")

    with_elec = sum(1 for i in items if i.get("electric_price"))
    with_water = sum(1 for i in items if i.get("water_price"))
    with_wifi = sum(1 for i in items if i.get("wifi_price"))
    with_other = sum(1 for i in items if i.get("other_utilities_price"))

    print("\nUtility Fields Coverage:")
    print(f"  - Electric price parsed : {with_elec:,}/{len(items):,} ({with_elec/len(items)*100:.1f}%)")
    print(f"  - Water price parsed    : {with_water:,}/{len(items):,} ({with_water/len(items)*100:.1f}%)")
    print(f"  - Wifi price parsed     : {with_wifi:,}/{len(items):,} ({with_wifi/len(items)*100:.1f}%)")
    print(f"  - Other services parsed : {with_other:,}/{len(items):,} ({with_other/len(items)*100:.1f}%)")
    print("=" * 60)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


DISTRICT_WARD_COORDS = {
    "Cầu Giấy": {
        "Dịch Vọng": (21.0315, 105.7925),
        "Dịch Vọng Hậu": (21.0375, 105.7875),
        "Mai Dịch": (21.0425, 105.7765),
        "Nghĩa Đô": (21.0495, 105.7985),
        "Nghĩa Tân": (21.0445, 105.7915),
        "Quan Hoa": (21.0345, 105.8015),
        "Trung Hòa": (21.0095, 105.7985),
        "Yên Hòa": (21.0215, 105.7945),
    },
    "Nam Từ Liêm": {
        "Mỹ Đình 1": (21.0195, 105.7755),
        "Mỹ Đình 2": (21.0315, 105.7715),
        "Mễ Trì": (21.0115, 105.7815),
        "Phú Đô": (21.0085, 105.7685),
        "Trung Văn": (20.9945, 105.7895),
        "Cầu Diễn": (21.0415, 105.7615),
        "Xuân Phương": (21.0325, 105.7395),
        "Phương Canh": (21.0425, 105.7425),
        "Tây Mỗ": (21.0025, 105.7485),
        "Đại Mỗ": (20.9915, 105.7615),
    },
    "Bắc Từ Liêm": {
        "Cổ Nhuế 1": (21.0545, 105.7835),
        "Cổ Nhuế 2": (21.0665, 105.7695),
        "Xuân Đỉnh": (21.0715, 105.7925),
        "Xuân Tảo": (21.0615, 105.7995),
        "Đông Ngạc": (21.0855, 105.7795),
        "Đức Thắng": (21.0775, 105.7725),
        "Phú Diễn": (21.0515, 105.7595),
        "Phúc Diễn": (21.0485, 105.7515),
        "Minh Khai": (21.0585, 105.7415),
        "Tây Tựu": (21.0595, 105.7235),
        "Thượng Cát": (21.0965, 105.7355),
        "Liên Mạc": (21.0915, 105.7545),
        "Thụy Phương": (21.0925, 105.7785),
    },
    "Thanh Xuân": {
        "Nhân Chính": (21.0065, 105.8085),
        "Thanh Xuân Bắc": (20.9985, 105.7965),
        "Thanh Xuân Nam": (20.9925, 105.7995),
        "Thanh Xuân Trung": (20.9995, 105.8065),
        "Thượng Đình": (21.0015, 105.8145),
        "Hạ Đình": (20.9915, 105.8115),
        "Khương Đình": (20.9885, 105.8185),
        "Khương Trung": (20.9995, 105.8215),
        "Khương Mai": (20.9995, 105.8295),
        "Kim Giang": (20.9815, 105.8165),
        "Phương Liệt": (20.9945, 105.8395),
    },
    "Đống Đa": {
        "Láng Thượng": (21.0265, 105.8045),
        "Láng Hạ": (21.0175, 105.8145),
        "Ô Chợ Dừa": (21.0185, 105.8265),
        "Thịnh Quang": (21.0085, 105.8185),
        "Trung Liệt": (21.0125, 105.8225),
        "Quang Trung": (21.0115, 105.8275),
        "Khương Thượng": (21.0065, 105.8275),
        "Kim Liên": (21.0095, 105.8365),
        "Phương Mai": (21.0035, 105.8395),
        "Phương Liên": (21.0125, 105.8395),
        "Trung Tự": (21.0095, 105.8315),
        "Nam Đồng": (21.0155, 105.8315),
        "Thổ Quan": (21.0185, 105.8335),
        "Khâm Thiên": (21.0215, 105.8355),
        "Văn Chương": (21.0225, 105.8325),
        "Hàng Bột": (21.0255, 105.8295),
        "Cát Linh": (21.0295, 105.8285),
        "Quốc Tử Giám": (21.0285, 105.8345),
        "Văn Miếu": (21.0285, 105.8385),
        "Ngã Tư Sở": (21.0045, 105.8195),
        "Trung Phụng": (21.0155, 105.8375),
    },
    "Ba Đình": {
        "Kim Mã": (21.0315, 105.8225),
        "Giảng Võ": (21.0265, 105.8185),
        "Ngọc Khánh": (21.0295, 105.8125),
        "Cống Vị": (21.0365, 105.8095),
        "Liễu Giai": (21.0395, 105.8145),
        "Vĩnh Phúc": (21.0425, 105.8075),
        "Ngọc Hà": (21.0385, 105.8245),
        "Đội Cấn": (21.0345, 105.8245),
        "Thành Công": (21.0215, 105.8145),
        "Điện Biên": (21.0315, 105.8365),
        "Quán Thánh": (21.0435, 105.8385),
        "Trúc Bạch": (21.0465, 105.8395),
        "Phúc Xá": (21.0505, 105.8455),
        "Nguyễn Trung Trực": (21.0445, 105.8445),
    },
    "Tây Hồ": {
        "Bưởi": (21.0485, 105.8085),
        "Thụy Khuê": (21.0455, 105.8245),
        "Yên Phụ": (21.0545, 105.8425),
        "Tứ Liên": (21.0665, 105.8445),
        "Quảng An": (21.0645, 105.8265),
        "Nhật Tân": (21.0815, 105.8195),
        "Phú Thượng": (21.0915, 105.8015),
        "Xuân La": (21.0595, 105.8045),
    },
    "Hoàng Mai": {
        "Định Công": (20.9785, 105.8215),
        "Đại Kim": (20.9745, 105.8145),
        "Hoàng Liệt": (20.9585, 105.8325),
        "Thịnh Liệt": (20.9715, 105.8395),
        "Giáp Bát": (20.9845, 105.8425),
        "Tương Mai": (20.9915, 105.8485),
        "Tân Mai": (20.9855, 105.8525),
        "Hoàng Văn Thụ": (20.9915, 105.8575),
        "Mai Động": (20.9965, 105.8645),
        "Vĩnh Hưng": (20.9895, 105.8775),
        "Lĩnh Nam": (20.9815, 105.8845),
        "Trần Phú": (20.9715, 105.8865),
        "Yên Sở": (20.9655, 105.8625),
        "Thanh Trì": (20.9845, 105.8945),
    },
    "Hai Bà Trưng": {
        "Bạch Đằng": (21.0115, 105.8655),
        "Thanh Lương": (21.0065, 105.8695),
        "Vĩnh Tuy": (20.9985, 105.8685),
        "Minh Khai": (20.9965, 105.8565),
        "Quỳnh Mai": (21.0025, 105.8575),
        "Quỳnh Lôi": (21.0025, 105.8515),
        "Thanh Nhàn": (21.0085, 105.8545),
        "Bạch Mai": (21.0045, 105.8485),
        "Bách Khoa": (21.0075, 105.8455),
        "Đồng Tâm": (20.9985, 105.8425),
        "Trương Định": (20.9945, 105.8455),
        "Lê Đại Hành": (21.0125, 105.8485),
        "Đồng Nhân": (21.0145, 105.8575),
        "Đống Mác": (21.0135, 105.8635),
        "Phố Huế": (21.0155, 105.8525),
        "Phạm Đình Hổ": (21.0175, 105.8585),
        "Nguyễn Du": (21.0195, 105.8475),
        "Cầu Dền": (21.0115, 105.8515),
    },
    "Hà Đông": {
        "Mộ Lao": (20.9825, 105.7865),
        "Văn Quán": (20.9765, 105.7895),
        "Vạn Phúc": (20.9815, 105.7765),
        "Hà Cầu": (20.9665, 105.7725),
        "La Khê": (20.9755, 105.7625),
        "Quang Trung": (20.9715, 105.7755),
        "Yết Kiêu": (20.9755, 105.7795),
        "Nguyễn Trãi": (20.9725, 105.7845),
        "Phúc La": (20.9695, 105.7945),
        "Kiến Hưng": (20.9545, 105.7925),
        "Phú La": (20.9595, 105.7655),
        "Phú Lương": (20.9465, 105.7785),
        "Phú Lãm": (20.9495, 105.7625),
        "Yên Nghĩa": (20.9485, 105.7425),
        "Dương Nội": (20.9715, 105.7455),
        "Đồng Mai": (20.9325, 105.7525),
        "Biên Giang": (20.9255, 105.7355),
    },
    "Hoàn Kiếm": {
        "Hàng Bạc": (21.0345, 105.8525),
        "Hàng Buồm": (21.0365, 105.8515),
        "Hàng Đào": (21.0335, 105.8495),
        "Hàng Gai": (21.0315, 105.8495),
        "Cửa Đông": (21.0335, 105.8445),
        "Cửa Nam": (21.0265, 105.8425),
        "Tràng Tiền": (21.0245, 105.8575),
        "Phan Chu Trinh": (21.0215, 105.8555),
        "Trần Hưng Đạo": (21.0225, 105.8485),
        "Chương Dương": (21.0295, 105.8615),
        "Phúc Tân": (21.0395, 105.8565),
        "Đồng Xuân": (21.0385, 105.8485),
    },
    "Long Biên": {
        "Bồ Đề": (21.0345, 105.8685),
        "Ngọc Lâm": (21.0445, 105.8685),
        "Gia Thụy": (21.0425, 105.8825),
        "Thượng Thanh": (21.0625, 105.8845),
        "Đức Giang": (21.0655, 105.8955),
        "Việt Hưng": (21.0565, 105.9045),
        "Phúc Đồng": (21.0365, 105.9025),
        "Sài Đồng": (21.0325, 105.9125),
        "Long Biên": (21.0245, 105.8895),
        "Thạch Bàn": (21.0185, 105.9125),
        "Cự Khối": (20.9985, 105.9055),
    },
    "Thanh Trì": {
        "Tân Triều": (20.9785, 105.7985),
        "Thanh Liệt": (20.9685, 105.8185),
        "Tả Thanh Oai": (20.9485, 105.8085),
        "Văn Điển": (20.9515, 105.8415),
        "Tứ Hiệp": (20.9425, 105.8515),
        "Tam Hiệp": (20.9545, 105.8315),
        "Ngọc Hồi": (20.9245, 105.8485),
        "Vĩnh Quỳnh": (20.9325, 105.8355),
    },
    "Hoài Đức": {
        "Vân Canh": (21.0285, 105.7285),
        "An Khánh": (20.9985, 105.7315),
        "Kim Chung": (21.0585, 105.7185),
        "Trạm Trôi": (21.0685, 105.7085),
        "Đức Thượng": (21.0825, 105.6985),
        "La Phù": (20.9785, 105.7385),
        "Đông La": (20.9685, 105.7485),
    },
    "Gia Lâm": {
        "Trâu Quỳ": (21.0085, 105.9325),
        "Đa Tốn": (20.9885, 105.9485),
        "Bát Tràng": (20.9785, 105.9125),
        "Yên Viên": (21.0785, 105.9125),
        "Đặng Xá": (21.0285, 105.9525),
    },
    "Đông Anh": {
        "Đông Anh": (21.1385, 105.8485),
        "Hải Bối": (21.0985, 105.8085),
        "Vĩnh Ngọc": (21.0885, 105.8285),
        "Kim Chung": (21.1185, 105.7785),
    }
}


def determine_ward_by_coords(district: str, lat: Any, lng: Any) -> str:
    if not lat or not lng:
        return ""
    try:
        f_lat = float(lat)
        f_lng = float(lng)
    except (ValueError, TypeError):
        return ""
    if not (20.5 < f_lat < 21.5 and 105.4 < f_lng < 106.3):
        return ""

    wards = DISTRICT_WARD_COORDS.get(district)
    if not wards:
        all_wards = {w: c for d_w in DISTRICT_WARD_COORDS.values() for w, c in d_w.items()}
        closest = min(all_wards.keys(), key=lambda w: haversine_km(f_lat, f_lng, all_wards[w][0], all_wards[w][1]))
        return closest
    closest = min(wards.keys(), key=lambda w: haversine_km(f_lat, f_lng, wards[w][0], wards[w][1]))
    return closest


def to_bool_int(v: Any) -> int:
    if isinstance(v, bool): return 1 if v else 0
    s = str(v).strip().lower()
    return 1 if s in ["true", "1", "t", "yes"] else 0


def parse_numeric_area(v: Any) -> Any:
    if not v: return ""
    s = str(v).strip().lower().replace("m2", "").replace("m²", "").strip()
    m = re.search(r"(\d+(?:[\.,]\d+)?)\s*-\s*(\d+(?:[\.,]\d+)?)", s)
    if m:
        n1 = float(m.group(1).replace(",", "."))
        n2 = float(m.group(2).replace(",", "."))
        avg = (n1 + n2) / 2.0
        return int(avg) if avg.is_integer() else round(avg, 1)
    m = re.search(r"(\d+(?:[\.,]\d+)?)", s)
    if m:
        n = float(m.group(1).replace(",", "."))
        return int(n) if n.is_integer() else round(n, 1)
    return ""


def parse_numeric_electric(v: Any) -> Any:
    if not v: return ""
    s = str(v).strip().lower()
    if "giá dân" in s: return 2500
    if any(k in s for k in ["miễn phí", "free"]): return 0
    m = re.search(r"(\d+(?:[\.,]\d+)?)\s*(k)?\s*-\s*(\d+(?:[\.,]\d+)?)\s*(k)?", s)
    if m:
        s1, k1, s2, k2 = m.group(1), m.group(2), m.group(3), m.group(4)
        n1 = float(s1.replace(".", "").replace(",", "."))
        n2 = float(s2.replace(".", "").replace(",", "."))
        if ("k" in s or k1 or k2) and n1 < 100: n1 *= 1000
        if ("k" in s or k1 or k2) and n2 < 100: n2 *= 1000
        if n1 < 10 and n2 < 10: n1 *= 1000; n2 *= 1000
        if n2 > 10000 and n1 <= 10000: return int(n1)
        return int((n1 + n2) / 2.0)
    m_dot = re.search(r"(\d{1,3}(?:\.\d{3})+)", s)
    if m_dot:
        n = int(m_dot.group(1).replace(".", ""))
        return n if n > 1 else ""
    m_k = re.search(r"(\d+(?:[\.,]\d+)?)\s*k\b", s)
    if m_k:
        return int(float(m_k.group(1).replace(".", "").replace(",", ".")) * 1000)
    m_4d = re.search(r"(\d{4,})", s)
    if m_4d: return int(m_4d.group(1))
    return ""


def parse_numeric_water(v: Any) -> Any:
    if not v: return ""
    s = str(v).strip().lower()
    if "giá dân" in s or "hóa đơn" in s: return 12000
    if any(k in s for k in ["miễn phí", "free"]): return 0
    m = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*(k)?\s*-\s*(\d{1,3}(?:\.\d{3})+|\d+)\s*(k)?", s)
    if m:
        s1, k1, s2, k2 = m.group(1), m.group(2), m.group(3), m.group(4)
        n1 = float(s1.replace(".", "").replace(",", "."))
        n2 = float(s2.replace(".", "").replace(",", "."))
        if ("k" in s or k1 or k2) and n1 < 100: n1 *= 1000
        if ("k" in s or k1 or k2) and n2 < 100: n2 *= 1000
        return int((n1 + n2) / 2.0)
    parts = s.split(";")
    for part in parts:
        m_dot = re.search(r"(\d{1,3}(?:\.\d{3})+)", part)
        if m_dot:
            n = int(m_dot.group(1).replace(".", ""))
            if n > 10: return n
        m_k = re.search(r"(\d+(?:[\.,]\d+)?)\s*k\b", part)
        if m_k:
            return int(float(m_k.group(1).replace(".", "").replace(",", ".")) * 1000)
        m_4d = re.search(r"(\d{4,})", part)
        if m_4d: return int(m_4d.group(1))
    return ""


def parse_numeric_money_field(v: Any) -> Any:
    if not v: return ""
    s = str(v).strip().lower()
    if "miễn phí" in s or "free" in s or re.search(r"(?:^|[^\d])0\s*đ", s):
        return 0
    m_range = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+k|\d{4,})\s*-\s*(\d{1,3}(?:\.\d{3})+|\d+k|\d{4,})", s)
    if m_range:
        p1, p2 = m_range.group(1), m_range.group(2)
        def to_n(p):
            if "k" in p: return float(p.replace("k", "")) * 1000
            return float(p.replace(".", ""))
        return int((to_n(p1) + to_n(p2)) / 2)
    m_dot = re.search(r"(\d{1,3}(?:\.\d{3})+)", s)
    if m_dot:
        return int(m_dot.group(1).replace(".", ""))
    m_k = re.search(r"(\d+(?:[\.,]\d+)?)\s*k\b", s)
    if m_k:
        return int(float(m_k.group(1).replace(",", ".")) * 1000)
    m_4d = re.search(r"(\d{4,})", s)
    if m_4d:
        return int(m_4d.group(1))
    if any(k in s for k in ["có sẵn", "có chỗ để xe", "khu để xe", "ô tô đỗ cửa", "giới hạn xe"]):
        return 0
    return ""


def clean_dataset_record(r: Dict[str, Any]) -> Dict[str, Any]:
    new_r = dict(r)
    
    # 1. Ward resolution using lat/lng
    cur_ward = (new_r.get("ward") or "").strip()
    if not cur_ward or cur_ward in DISTRICT_WARD_COORDS:
        res_ward = determine_ward_by_coords(new_r.get("district", ""), new_r.get("latitude"), new_r.get("longitude"))
        if res_ward:
            new_r["ward"] = res_ward
        elif cur_ward in DISTRICT_WARD_COORDS:
            new_r["ward"] = ""
    if new_r.get("listing_id") == "RC_31430":
        new_r["ward"] = "Bạch Đằng"

    # Sanitize placeholder coordinates (e.g. default map boundary 85.0511, -180.0)
    try:
        lat_f = float(new_r.get("latitude", 0))
        lng_f = float(new_r.get("longitude", 0))
        if lat_f > 80 or lng_f < 0 or lat_f < 10:
            dist = new_r.get("district", "")
            ward = new_r.get("ward", "")
            if dist in DISTRICT_WARD_COORDS and ward in DISTRICT_WARD_COORDS[dist]:
                c_lat, c_lng = DISTRICT_WARD_COORDS[dist][ward]
                new_r["latitude"] = str(c_lat)
                new_r["longitude"] = str(c_lng)
            elif dist in DISTRICT_WARD_COORDS:
                first_ward = list(DISTRICT_WARD_COORDS[dist].keys())[0]
                c_lat, c_lng = DISTRICT_WARD_COORDS[dist][first_ward]
                new_r["latitude"] = str(c_lat)
                new_r["longitude"] = str(c_lng)
    except (ValueError, TypeError):
        pass

    # 2. Parse numerical fields
    new_r["area_m2"] = parse_numeric_area(r.get("area_m2"))
    new_r["electric_price"] = parse_numeric_electric(r.get("electric_price"))
    new_r["water_price"] = parse_numeric_water(r.get("water_price"))
    new_r["wifi_price"] = parse_numeric_money_field(r.get("wifi_price"))
    new_r["parking_fee"] = parse_numeric_money_field(r.get("parking_fee"))
    new_r["other_utilities_price"] = parse_numeric_money_field(r.get("other_utilities_price"))

    # 3. Amenity flags as binary 1/0 (dropped fire_safety)
    bool_cols = [
        "air_conditioner", "water_heater", "refrigerator", "washing_machine",
        "elevator", "balcony_window", "pet_allowed"
    ]
    for b in bool_cols:
        new_r[b] = to_bool_int(r.get(b))

    # 4. Drop contact_name, contact_zalo
    new_r.pop("contact_name", None)
    new_r.pop("contact_zalo", None)

    return new_r


def main():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    data_dir = os.path.join(project_root, "data")
    yh_file = os.path.join(data_dir, "rooms_ha-noi.json")
    ren_file = os.path.join(data_dir, "rooms_rencity_hanoi.json")
    pt_file = os.path.join(data_dir, "rooms_phongtot_hanoi.json")

    all_unified = []
    if os.path.exists(yh_file):
        all_unified.extend(process_yourhome(yh_file))
    if os.path.exists(ren_file):
        all_unified.extend(process_rencity(ren_file))
    if os.path.exists(pt_file):
        all_unified.extend(process_phongtot(pt_file))

    # Apply complete numerical cleaning, ward determination, and column drops
    all_unified = [clean_dataset_record(item) for item in all_unified]

    # Drop all rows containing any missing/unresolved values across any columns
    missing_indicators = {'', 'none', 'null', 'nan', 'chưa rõ', '$undefined', 'undefined'}
    clean_unified = [
        r for r in all_unified
        if not any(str(r.get(col, '')).strip().lower() in missing_indicators for col in UNIFIED_HEADERS)
    ]
    print(f"Dropped {len(all_unified) - len(clean_unified)} listings with missing values. Kept {len(clean_unified)} complete listings.")

    out_csv = os.path.join(data_dir, "unified_hanoi_rentals.csv")
    out_json = os.path.join(data_dir, "unified_hanoi_rentals.json")

    save_unified_csv(clean_unified, out_csv)
    save_unified_json(clean_unified, out_json)
    print_overall_summary(clean_unified)


if __name__ == "__main__":
    main()
