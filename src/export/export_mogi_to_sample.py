import csv
import gzip
import logging
import os
import re
from pathlib import Path

from bs4 import BeautifulSoup

from src.export.text_features import extract_amenity_features, extract_utility_prices, get_amenities_list
from src.parse.mogi_parser import parse_detail_page

# Regex for unmasked phone
_PHONE_RE = re.compile(r"PhoneFormat\('(\d{9,11})'\)")
_AGENT_HREF_RE = re.compile(r"/moi-gioi/(\d{9,11})-[^\"']*")

def main():
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("export")

    raw_dir = Path("data/raw/html/mogi")
    out_csv = Path("mogi_hanoi_extracted.csv")

    columns = [
        "platform", "listing_id", "title", "district", "ward", "address", 
        "price_vnd", "house_type", "area_m2", "electric_price", "water_price", 
        "wifi_price", "other_utilities_price", "parking_fee", "air_conditioner", 
        "water_heater", "refrigerator", "washing_machine", "elevator", 
        "balcony_window", "fire_safety", "pet_allowed", "amenities_list", 
        "latitude", "longitude", "contact_name", "contact_phone", "contact_zalo", 
        "image_count", "image_urls", "listing_url"
    ]

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
                
                # We need a dummy URL for the parser
                url = f"https://mogi.vn/dummy-id{filepath.name.replace('mogi_', '').replace('.html.gz', '')}"
                parsed = parse_detail_page(html, url)
                
                # Check if it's Ha Noi
                if parsed.get("province") != "Hà Nội":
                    continue
                
                hanoi_count += 1

                # Phone extraction
                soup = BeautifulSoup(html, "lxml")
                agent_name_el = soup.select_one(".agent-info .agent-name a")
                agent_href = agent_name_el.get("href") if agent_name_el else None
                phone_match = _PHONE_RE.search(html) or (_AGENT_HREF_RE.search(agent_href) if agent_href else None)
                phone = phone_match.group(1) if phone_match else ""

                desc = parsed.get("description", "") or ""

                features = extract_amenity_features(desc)
                utils = extract_utility_prices(desc)
                amenities = get_amenities_list(features)

                # Extract ward from breadcrumb if possible
                ward = ""
                breadcrumb = [li.get_text(strip=True) for li in soup.select("ul.breadcrumb li span")]
                if len(breadcrumb) >= 5:
                    ward = breadcrumb[4]

                row = {
                    "platform": "Mogi.vn",
                    "listing_id": parsed.get("listing_id", ""),
                    "title": parsed.get("title", ""),
                    "district": parsed.get("district", ""),
                    "ward": ward,
                    "address": parsed.get("address_raw", ""),
                    "price_vnd": parsed.get("price_vnd_month", ""),
                    "house_type": parsed.get("room_type", "Nhà trọ"),
                    "area_m2": parsed.get("area_m2", ""),
                    "electric_price": utils["electric_price"],
                    "water_price": utils["water_price"],
                    "wifi_price": utils["wifi_price"],
                    "other_utilities_price": utils["other_utilities_price"],
                    "parking_fee": utils["parking_fee"],
                    "air_conditioner": features["air_conditioner"],
                    "water_heater": features["water_heater"],
                    "refrigerator": features["refrigerator"],
                    "washing_machine": features["washing_machine"],
                    "elevator": features["elevator"],
                    "balcony_window": features["balcony_window"],
                    "fire_safety": features["fire_safety"],
                    "pet_allowed": features["pet_allowed"],
                    "amenities_list": amenities,
                    "latitude": parsed.get("lat", ""),
                    "longitude": parsed.get("lon", ""),
                    "contact_name": parsed.get("poster_name", ""),
                    "contact_phone": phone,
                    "contact_zalo": phone,
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
