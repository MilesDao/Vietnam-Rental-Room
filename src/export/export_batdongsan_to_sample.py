import csv
import gzip
import logging
import os
import re
from pathlib import Path

from bs4 import BeautifulSoup

from src.parse.batdongsan_parser import parse_detail_page

# Utilities extraction regexes
RE_ELEC = re.compile(r"(?i)(điện\s*[:\s]*\d+[\.,]?\d*\s*k?(?:/số|/kw)?|điện\s*giá\s*dân)")
RE_WATER = re.compile(r"(?i)(nước\s*[:\s]*\d+[\.,]?\d*\s*k?(?:/người|/khối|/tháng)?|nước\s*giá\s*dân)")
RE_WIFI = re.compile(r"(?i)(wifi|internet|mạng)\s*[:\s]*(\d+[\.,]?\d*\s*k?(?:/phòng|/tháng|/người)?|miễn\s*phí|free)")
RE_PARKING = re.compile(r"(?i)(để\s*xe|gửi\s*xe|xe\s*máy)\s*[:\s]*(\d+[\.,]?\d*\s*k?(?:/xe|/tháng)?|miễn\s*phí|free)")
RE_SERVICE = re.compile(r"(?i)(phí\s*dịch\s*vụ|dịch\s*vụ|vệ\s*sinh)\s*[:\s]*(\d+[\.,]?\d*\s*k?(?:/người|/phòng|/tháng)?|miễn\s*phí|free)")

def has_keyword(text, keywords):
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)

def get_amenities_list(features):
    mapping = {
        "air_conditioner": "Điều hòa",
        "water_heater": "Nóng lạnh",
        "refrigerator": "Tủ lạnh",
        "washing_machine": "Máy giặt",
        "elevator": "Thang máy",
        "balcony_window": "Ban công/Cửa sổ",
        "fire_safety": "PCCC",
        "pet_allowed": "Thú cưng"
    }
    return "; ".join([mapping[k] for k, v in features.items() if v and k in mapping])

def main():
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("export_bds")

    raw_dir = Path("data/raw/html/batdongsan")
    out_csv = Path("batdongsan_hanoi_extracted.csv")

    columns = [
        "platform", "listing_id", "title", "district", "ward", "address", 
        "price_vnd", "house_type", "area_m2", "electric_price", "water_price", 
        "wifi_price", "other_utilities_price", "parking_fee", "air_conditioner", 
        "water_heater", "refrigerator", "washing_machine", "elevator", 
        "balcony_window", "fire_safety", "pet_allowed", "amenities_list", 
        "latitude", "longitude", "contact_name", "contact_phone", "contact_zalo", 
        "image_count", "image_urls", "listing_url"
    ]

    if not raw_dir.exists():
        log.warning(f"Directory {raw_dir} does not exist. Writing empty CSV.")
        with open(out_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
        return

    html_files = list(raw_dir.rglob("*.html.gz"))
    log.info(f"Found {len(html_files)} HTML files to process.")

    processed = 0
    hanoi_count = 0

    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()

        for filepath in html_files:
            try:
                with gzip.open(filepath, "rt", encoding="utf-8") as gz:
                    html = gz.read()
                
                # Reconstruct dummy URL
                native_id = filepath.name.replace('bds_', '').replace('.html.gz', '')
                url = f"https://batdongsan.com.vn/dummy-pr{native_id}"
                
                parsed = parse_detail_page(html, url)
                
                if parsed.get("province") != "Hà Nội":
                    continue
                
                hanoi_count += 1
                desc = parsed.get("description", "") or ""
                
                features = {
                    "air_conditioner": has_keyword(desc, ["điều hòa", "máy lạnh", "dieu hoa", "may lanh"]),
                    "water_heater": has_keyword(desc, ["nóng lạnh", "nong lanh", "bình nóng", "máy nước nóng"]),
                    "refrigerator": has_keyword(desc, ["tủ lạnh", "tu lanh"]),
                    "washing_machine": has_keyword(desc, ["máy giặt", "may giat"]),
                    "elevator": has_keyword(desc, ["thang máy", "thang may"]),
                    "balcony_window": has_keyword(desc, ["ban công", "ban cong", "cửa sổ", "cua so"]),
                    "fire_safety": has_keyword(desc, ["pccc", "thoát hiểm", "chữa cháy", "cứu hỏa", "phòng cháy"]),
                    "pet_allowed": has_keyword(desc, ["thú cưng", "chó mèo", "pet"])
                }

                elec_m = RE_ELEC.search(desc)
                water_m = RE_WATER.search(desc)
                wifi_m = RE_WIFI.search(desc)
                parking_m = RE_PARKING.search(desc)
                service_m = RE_SERVICE.search(desc)

                amenities = get_amenities_list(features)

                # Convert price text to somewhat VND, rough approximation:
                # Batdongsan has text like "3.5 triệu/tháng" -> 3500000
                price_text = parsed.get("price_raw", "")
                price_vnd = ""
                if "triệu" in price_text:
                    try:
                        num = float(price_text.split("triệu")[0].strip().replace(",", "."))
                        price_vnd = str(int(num * 1000000))
                    except:
                        pass
                
                # Convert area
                area_text = parsed.get("area_raw", "")
                area_m2 = ""
                m_area = re.search(r"(\d+[\.,]?\d*)\s*m", area_text)
                if m_area:
                    area_m2 = m_area.group(1).replace(",", ".")

                row = {
                    "platform": "Batdongsan.com.vn",
                    "listing_id": parsed.get("listing_id", ""),
                    "title": parsed.get("title", ""),
                    "district": parsed.get("district", ""),
                    "ward": "",
                    "address": parsed.get("address_raw", ""),
                    "price_vnd": price_vnd,
                    "house_type": parsed.get("room_type", "Nhà trọ"),
                    "area_m2": area_m2,
                    "electric_price": elec_m.group(0).strip() if elec_m else "",
                    "water_price": water_m.group(0).strip() if water_m else "",
                    "wifi_price": wifi_m.group(0).strip() if wifi_m else "",
                    "other_utilities_price": service_m.group(0).strip() if service_m else "",
                    "parking_fee": parking_m.group(0).strip() if parking_m else "",
                    "air_conditioner": features["air_conditioner"],
                    "water_heater": features["water_heater"],
                    "refrigerator": features["refrigerator"],
                    "washing_machine": features["washing_machine"],
                    "elevator": features["elevator"],
                    "balcony_window": features["balcony_window"],
                    "fire_safety": features["fire_safety"],
                    "pet_allowed": features["pet_allowed"],
                    "amenities_list": amenities,
                    "latitude": "",
                    "longitude": "",
                    "contact_name": parsed.get("poster_name", ""),
                    "contact_phone": parsed.get("phone", ""),
                    "contact_zalo": parsed.get("phone", ""),
                    "image_count": parsed.get("n_images", 0),
                    "image_urls": " | ".join(parsed.get("image_urls", [])),
                    "listing_url": url,
                }
                writer.writerow(row)
            except Exception as e:
                log.error(f"Error processing {filepath}: {e}")
            
            processed += 1
            if processed % 100 == 0:
                log.info(f"Processed {processed} / {len(html_files)} ...")
    
    log.info(f"Done! Extracted {hanoi_count} Hanoi records to {out_csv.name}")

if __name__ == "__main__":
    main()
