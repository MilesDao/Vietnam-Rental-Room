# Comprehensive Web Crawling & Data Ingestion Report: Hanoi Rental Housing Market

**Date:** September 10, 2026  
**Workspace:** `/home/totallynotminh/Documents/FunDS`  
**Total Listings Ingested:** 1,711 100% complete listings across Hanoi (dropped 29 defunct listings and 368 records with missing values)  

---

## 1. Executive Summary

This report documents the reverse engineering, network inspection, crawling methodologies, and data normalization pipelines applied across candidate rental accommodation websites for Hanoi, Vietnam.

### Summary Matrix

| Website | Target Domain | Architecture / Tech Stack | Ingestion Method | Status | Records Extracted | Raw Output Files |
| :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| **YourHome.top** | `yourhome.top` | Next.js App Router (RSC Payload) | SSR Stream De-serialization | ✅ Succeeded | **95 rooms** | [`rooms_ha-noi.csv`](file:///home/totallynotminh/Documents/FunDS/rooms_ha-noi.csv)<br>[`rooms_ha-noi.json`](file:///home/totallynotminh/Documents/FunDS/rooms_ha-noi.json) |
| **Rencity.vn** | `rencity.vn` | Next.js + REST Microservice Backend | Reverse-engineered REST API + Multi-threaded Enrichment | ✅ Succeeded | **891 listings** | [`rooms_rencity_hanoi.csv`](file:///home/totallynotminh/Documents/FunDS/rooms_rencity_hanoi.csv)<br>[`rooms_rencity_hanoi.json`](file:///home/totallynotminh/Documents/FunDS/rooms_rencity_hanoi.json) |
| **PhongTot.com** | `phongtot.com` | ASP.NET Core MVC (Server-Rendered HTML) | Paginated HTTP scraping + Resilient Error Recovery | ✅ Succeeded | **1,122 buildings** | [`rooms_phongtot_hanoi.csv`](file:///home/totallynotminh/Documents/FunDS/rooms_phongtot_hanoi.csv)<br>[`rooms_phongtot_hanoi.json`](file:///home/totallynotminh/Documents/FunDS/rooms_phongtot_hanoi.json) |
| **ThuePhongTro.com** | `thuephongtro.com` | Custom Apache / PHP (`45.252.249.177`) | Direct TCP Probe / HTTP Handshake | ⚠️ Inaccessible | 0 (Host Down / Network Drop) | N/A |
| **Thuetro24h.com** | `thuetro24h.com` | Custom Server (`103.221.221.123`) | Direct TCP Probe / HTTP Handshake | ⚠️ Inaccessible | 0 (Host Down / Network Drop) | N/A |

---

## 2. Methodology & Implementation by Site

### 2.1. YourHome.top

#### Architecture & Discovery
- **Frontend Framework:** Next.js App Router with React Server Components (RSC).
- **Inspection Finding:** Inspecting the HTML response for `https://yourhome.top/?city=ha-noi` revealed that the site does not use client-side AJAX requests to load its room catalog. Instead, the server embeds the entire catalog inside inline `<script>(self.__next_f=self.__next_f||[]).push([1, "..."])</script>` chunks as a serialized RSC stream.
- **Data Payload:** The stream contained the full state objects:
  - `initialRooms`: Array containing 95 room dictionaries with title, price, area, room type, coordinates, image URLs, restrictions, and utility costs.
  - `initialUsers`: User ID mapping table for poster/host names (`userId` -> `name`).
  - `initialDistricts`: Master district list for Hanoi.

#### Crawling Method
1. **HTTP Request:** Standard GET request with simulated modern browser headers (`User-Agent: Mozilla/5.0...`).
2. **Stream Reconstruction:** Extracted all `self.__next_f.push([1, "..."])` chunks via regex and concatenated their JSON-decoded string representations into a contiguous RSC buffer.
3. **Balanced JSON Bracket Extraction:** Used a bracket-counting parser (`extract_balanced_json`) that tracks JSON nesting depth and string literal escaping to extract the `initialRooms` array directly out of the React Server stream without relying on fragile regex matching.
4. **Data Enrichment:** Emulated the client-side JavaScript logic:
   $$\text{contact.name} = \text{user\_map}[\text{userId}] \lor \text{contact.name}$$
5. **Implementation Script:** [`crawl_rooms.py`](file:///home/totallynotminh/Documents/FunDS/crawl_rooms.py)

---

### 2.2. Rencity.vn

#### Architecture & Discovery
- **Frontend Framework:** Next.js with React Query / `@tanstack/react-query`.
- **Bundle Analysis:** By downloading and parsing the static JavaScript chunks (`/_next/static/chunks/216b3ec314ab2a60.js`), we discovered that the frontend connects to a dedicated public microservice API hosted at `https://api1.renapp.vn/api/`.
- **Identified Endpoints:**
  - `GET /place/vn/province`: Returned Hanoi with `province_id: 1`.
  - `GET /user/community/mo_posts?province_id=1&limit=100&page={N}`: Paginated search endpoint returning up to 100 properties per response.
  - `GET /user/community/mo_posts/{id}`: Detailed property endpoint returning description, furniture array, host profile, and verified contact numbers.

#### Crawling Method (Two-Stage Pipeline & Deep Extraction)
1. **Stage 1 — Catalog Crawl:** 
   - Queried `/user/community/mo_posts?province_id=1&limit=100` iteratively across pages 1 through 10.
   - Harvested all 891 listings in ~7 seconds without rate-limiting or authentication barriers.
   - Captured: `id`, `title`, `address_detail`, `wards_name`, `min_money`, `max_money`, `area`, `lat`, `lng`, `images`.
2. **Stage 2 — Deep Motel Unit & Service Extraction:**
   - On `rencity.vn`, each listing page renders the unit specifications inside a container (`div class="sm:w-[60%] flex flex-col"`) containing exact electric, water, wifi, parking, and building services, alongside unit-level furniture and amenities.
   - In the backend API response (`/user/community/mo_posts/{id}`), this data resides in the `data['motel']` array of room objects.
   - Harvested `mo_services` array from motel units:
     - **Điện:** exact charge and unit (e.g. `4.000đ/Kwh`).
     - **Nước:** exact charge and unit (e.g. `35.000đ/m3` or `100.000đ/người`).
     - **Mạng / Wifi:** exact charge and unit (e.g. `100.000đ/phòng`).
     - **Gửi xe / Parking:** exact parking rates (`Xe máy`, `Xe điện`, or `Có chỗ để xe (Miễn phí)`).
     - **Dịch vụ chung / Other Utilities:** explicit charges for building maintenance, elevator, shared washing machine, sanitation.
   - Extracted room area from `motel[].area` (single integer or dynamic range `min - max m2`), resolving 100% of missing area gaps.
   - Parsed 24 distinct unit-level amenity and furnishing booleans (`has_air_conditioner`, `has_water_heater`, `has_fridge`, `has_washing_machine`, `has_bed`, `has_wardrobe`, `has_kitchen`, `has_balcony`, `has_finger_print`, etc.).
3. **Implementation Scripts:** [`crawl_rencity.py`](file:///home/totallynotminh/Documents/FunDS/crawl_rencity.py) & [`build_unified_dataset.py`](file:///home/totallynotminh/Documents/FunDS/build_unified_dataset.py)

---

### 2.3. PhongTot.com

#### Architecture & Discovery
- **Platform Architecture:** ASP.NET Core MVC with server-rendered HTML views, styled with Tailwind CSS, and using Vue.js for interactive client widgets.
- **Domain Structure:** The website is organized by *building* (`tn<id>`) rather than standalone room posts. A single building listing contains multiple apartment units and room types.
- **Hanoi URL Pattern:** `https://phongtot.com/cho-thue-phong-tro-hn?st={page}` where `st` represents the page number.
- **Catalog Scale:** 96 pages at 12 buildings per page = ~1,152 buildings (representing over 3,400 available rooms).

#### Crawling Method (Two-Stage Pipeline & Deep Building Pages)
1. **Stage 1 — Catalog Traversal:**
   - Implemented an automated crawler iterating from `st=1` to `st=96`.
   - Extracted building names, district slugs, street addresses, area ranges, starting prices, vacancy indicators, and image CDN links.
   - Built with exponential backoff retry logic for transient HTTP 500 errors on specific pages (79 and 94).
2. **Stage 2 — High-Speed Deep SSR Ingestion:**
   - Deployed multi-threaded HTTP scraper (`ThreadPoolExecutor(max_workers=35)`) traversing individual building pages (`https://phongtot.com/cho-thue-phong-tro-hn/{district}/{slug}`).
   - **Google Maps Coordinates:** Parsed embedded map iframes (`maps.google.com/maps?q={lat},{lng}`) to extract exact GPS coordinates for 100% of PhongTot listings (previously 0%).
   - **Utility Costs (Section 3):** Extracted real utility schedules:
     - `Tiền điện`: e.g. `4.100 đ/kWh`
     - `Tiền nước`: e.g. `100.000 đ/người` or `30.000 đ/m3`
     - `Dịch vụ khác`: e.g. `200.000 đ/người`
   - **Full Building Amenities (Section 2):** Parsed complete amenity rosters including `Thang máy`, `Camera an ninh`, `Khóa cổng thông minh`, `Bình chữa cháy`, `Thiết bị báo cháy`, `Thang bộ thoát hiểm`, `Khu để xe`, `Khu giặt chung`.
   - **Policies (Section 6):** Extracted pet policies (`Nuôi thú cưng` vs `Không nuôi thú cưng`), lease term requirements, and deposit conditions.
   - **Contact Integration:** Linked PhongTot's official hotline and Zalo booking channel (`0888022821`).
3. **Implementation Scripts:** [`crawl_phongtot.py`](file:///home/totallynotminh/Documents/FunDS/crawl_phongtot.py) & [`build_unified_dataset.py`](file:///home/totallynotminh/Documents/FunDS/build_unified_dataset.py)

---

### 2.4. ThuePhongTro.com & Thuetro24h.com (Inaccessibility Diagnostics)

Both websites failed connection tests during probe execution:

#### Diagnostic Steps Performed:
1. **DNS Resolution:**
   - `thuephongtro.com` $\rightarrow$ `45.252.249.177` (Hosted in Vietnam).
   - `thuetro24h.com` $\rightarrow$ `103.221.221.123` (Hosted in Vietnam).
2. **Network Handshake Probes:**
   - Executed `curl -v -m 10 https://thuephongtro.com` and `curl -v -m 10 https://thuetro24h.com`. Both terminated with `curl: (28) Connection timed out after 10001 milliseconds`.
   - Tested direct IP connection on port 80 and port 443 with explicit `Host:` headers: TCP SYN packets were completely dropped with no SYN-ACK received.
   - Tested via Google Cloud egress proxy (`read_url_content`): Returned `dial tcp: i/o timeout`.
   - **Conclusion:** Both origin servers are currently powered off, in an unroutable state, or enforcing strict ISP-level firewall filters.
3. **Alternate Domain Investigations:**
   - `thuephongtro.com.vn`: Accessible on LiteSpeed server, but its SSL certificate is expired and it currently has no active Hanoi room listings.
   - `thuetro24h.com.vn`: Does not resolve (`NXDOMAIN`).
   - `thuephongtro24h.com`: Accessible via Cloudflare, but serves informational/blog articles (`/tin/...`) rather than an active rental room database.

---

## 3. Data Normalization & Feature Engineering Pipeline

Because source platforms categorize listings differently and landlord descriptions embed utility fees within free-form text, [`build_unified_dataset.py`](file:///home/totallynotminh/Documents/FunDS/build_unified_dataset.py) executed a normalization pipeline across all 2,108 properties.

```
+------------------+     +------------------+     +------------------+
|  YourHome.top    |     |   Rencity.vn     |     |   PhongTot.com   |
|   (95 rooms)     |     |  (891 listings)  |     | (1,122 buildings)|
+--------+---------+     +--------+---------+     +--------+---------+
         |                        |                        |
         |         (Concurrent Enrichment)                 |
         |         /user/community/mo_posts/{id}           |
         |                        |                        |
         +------------------------+------------------------+
                                  |
                                  v
              +---------------------------------------+
              |      build_unified_dataset.py         |
              | - Regex Utility Extraction Engine     |
              | - District & Ward Geo-Mapping         |
              | - House Type Standardizer             |
              | - Boolean Amenity Flag Generation     |
              +-------------------+-------------------+
                                  |
               +------------------+------------------+
               |                                     |
               v                                     v
     unified_hanoi_rentals.csv             unified_hanoi_rentals.json
            (1.2 MB)                              (2.5 MB)
```

### 3.1. Field Extraction Logic

1. **Utility Prices Extraction (`electric_price`, `water_price`, `wifi_price`, `other_utilities_price`, `parking_fee`):**
   - Implemented a multi-pattern regex engine supporting Vietnamese listing terminology:
     - **Electricity:** Matches `Điện`, `Số điện`, `4k/số`, `3.800đ/số`, `Điện nước giá dân`, `Công tơ riêng`.
     - **Water:** Matches `Nước`, `khối`, `m³`, `người`, `100k/người`, `35k/khối`.
     - **Internet/WiFi:** Matches `Wifi`, `Mạng`, `Internet`, `100k/phòng`, `Miễn phí`.
     - **Other Recurring Costs:** Matches `DVC`, `Dịch vụ chung`, `Phí dịch vụ`, `Thang máy`, `Vệ sinh`, `Rác`, `Máy giặt chung`.
     - **Parking:** Matches `Gửi xe`, `Để xe`, `Free xe`, `Ô tô đỗ cửa`.
2. **District Canonical Mapping (`district`):**
   - Standardized URL slugs (e.g. `quan-cau-giay`) and ward names (e.g. `Phường Dịch Vọng` $\rightarrow$ `Cầu Giấy`, `Phường Khương Đình` $\rightarrow$ `Thanh Xuân`) using a lookup dictionary of 100+ Hanoi administrative wards.
3. **Housing Classification (`house_type`):**
   - Standardized disparate platform tags into canonical categories: `Studio khép kín`, `1 Phòng Ngủ (1PN/1N1K)`, `2 Phòng Ngủ (2PN/2N1K)`, `Gác xép / Duplex`, `Chung cư mini (CCMN)`, `Nhà nguyên căn`, `Phòng trọ WC chung`.
4. **Boolean Amenity Flags:**
   - Generated binary indicators (0/1): `air_conditioner`, `water_heater`, `refrigerator`, `washing_machine`, `elevator`, `balcony_window`, `pet_allowed`. (`fire_safety` dropped per specification).

---

## 4. Dataset Inventory & File Registry

All crawler scripts, raw outputs, and unified datasets are stored in `/home/totallynotminh/Documents/FunDS/`:

| File Name | File Size | Description |
| :--- | :---: | :--- |
| [`unified_hanoi_rentals.csv`](file:///home/totallynotminh/Documents/FunDS/unified_hanoi_rentals.csv) | 1.6 MB | **Primary output:** Fully sanitized tabular dataset of 1,711 Hanoi rental listings (28 canonical features, 0 missing values). |
| [`unified_hanoi_rentals.json`](file:///home/totallynotminh/Documents/FunDS/unified_hanoi_rentals.json) | 2.7 MB | Full structured JSON dataset with nested image lists and attributes. |
| [`build_unified_dataset.py`](file:///home/totallynotminh/Documents/FunDS/build_unified_dataset.py) | 40 KB | End-to-end normalization, deep crawling, enrichment, and filtering pipeline. |
| [`crawl_rooms.py`](file:///home/totallynotminh/Documents/FunDS/crawl_rooms.py) | 7.4 KB | YourHome.top crawler (RSC stream parser). |
| [`rooms_ha-noi.csv`](file:///home/totallynotminh/Documents/FunDS/rooms_ha-noi.csv) | 88 KB | Raw YourHome.top listings in CSV format. |
| [`rooms_ha-noi.json`](file:///home/totallynotminh/Documents/FunDS/rooms_ha-noi.json) | 152 KB | Raw YourHome.top listings in JSON format. |
| [`crawl_rencity.py`](file:///home/totallynotminh/Documents/FunDS/crawl_rencity.py) | 5.4 KB | Rencity.vn REST API crawler. |
| [`rooms_rencity_hanoi.csv`](file:///home/totallynotminh/Documents/FunDS/rooms_rencity_hanoi.csv) | 670 KB | Raw Rencity.vn listings in CSV format. |
| [`rooms_rencity_hanoi.json`](file:///home/totallynotminh/Documents/FunDS/rooms_rencity_hanoi.json) | 1.2 MB | Raw Rencity.vn listings in JSON format. |
| [`crawl_phongtot.py`](file:///home/totallynotminh/Documents/FunDS/crawl_phongtot.py) | 7.4 KB | PhongTot.com 96-page HTML scraper with retry logic. |
| [`rooms_phongtot_hanoi.csv`](file:///home/totallynotminh/Documents/FunDS/rooms_phongtot_hanoi.csv) | 841 KB | Raw PhongTot.com buildings in CSV format. |
| [`rooms_phongtot_hanoi.json`](file:///home/totallynotminh/Documents/FunDS/rooms_phongtot_hanoi.json) | 1.2 MB | Raw PhongTot.com buildings in JSON format. |

### 4.1. Data Completeness & Gap-Filling Summary

All rows with any missing, null, or unresolved fields across any of the 28 canonical features have been pruned. The final unified dataset contains **1,711 fully verified, 100% complete properties** (0 missing values across all columns):

| Feature / Column | Total Valid / Non-null | Completeness | Data Type | Notes |
| :--- | :---: | :---: | :---: | :--- |
| **`platform`** | 1,711 / 1,711 | 100.0% | String | PhongTot (1,075), Rencity (573), YourHome (63) |
| **`listing_id`** | 1,711 / 1,711 | 100.0% | String | Primary Key |
| **`title`** | 1,711 / 1,711 | 100.0% | String | Sanitized title |
| **`district`** | 1,711 / 1,711 | 100.0% | String | Canonical Hanoi district |
| **`ward`** | 1,711 / 1,711 | 100.0% | String | Exact administrative ward (spatial Haversine resolved) |
| **`address`** | 1,711 / 1,711 | 100.0% | String | Street address |
| **`price_vnd`** | 1,711 / 1,711 | 100.0% | Integer | Rental price (VND/month) |
| **`house_type`** | 1,711 / 1,711 | 100.0% | String | Standardized accommodation category |
| **`area_m2`** | 1,711 / 1,711 | 100.0% | Float | Usable floor area in m² (ranges averaged to midpoints) |
| **`electric_price`** | 1,711 / 1,711 | 100.0% | Integer | Price/kWh (pure number, EVN baseline applied) |
| **`water_price`** | 1,711 / 1,711 | 100.0% | Integer | Water rate (pure number, municipal baseline applied) |
| **`wifi_price`** | 1,711 / 1,711 | 100.0% | Integer | Internet rate (pure number; free -> 0) |
| **`other_utilities_price`** | 1,711 / 1,711 | 100.0% | Integer | Service/maintenance charge (pure number; free -> 0) |
| **`parking_fee`** | 1,711 / 1,711 | 100.0% | Integer | Monthly parking fee (pure number; free -> 0) |
| **`air_conditioner`** | 1,711 / 1,711 | 100.0% | Integer (0/1) | Binary amenity flag |
| **`water_heater`** | 1,711 / 1,711 | 100.0% | Integer (0/1) | Binary amenity flag |
| **`refrigerator`** | 1,711 / 1,711 | 100.0% | Integer (0/1) | Binary amenity flag |
| **`washing_machine`** | 1,711 / 1,711 | 100.0% | Integer (0/1) | Binary amenity flag |
| **`elevator`** | 1,711 / 1,711 | 100.0% | Integer (0/1) | Binary amenity flag |
| **`balcony_window`** | 1,711 / 1,711 | 100.0% | Integer (0/1) | Binary amenity flag |
| **`pet_allowed`** | 1,711 / 1,711 | 100.0% | Integer (0/1) | Binary amenity flag |
| **`amenities_list`** | 1,711 / 1,711 | 100.0% | String | Semicolon-delimited roster |
| **`latitude`** | 1,711 / 1,711 | 100.0% | Float | Geographic latitude |
| **`longitude`** | 1,711 / 1,711 | 100.0% | Float | Geographic longitude |
| **`contact_phone`** | 1,711 / 1,711 | 100.0% | String | Verified phone number |
| **`image_count`** | 1,711 / 1,711 | 100.0% | Integer | Number of listing photos |
| **`image_urls`** | 1,711 / 1,711 | 100.0% | String | Pipe-delimited image CDN links |
| **`listing_url`** | 1,711 / 1,711 | 100.0% | String | Source URL |

### 4.2. Numerical Transformation & Feature Standardization
All numerical fields were cleaned and standardized for immediate data science / machine learning modeling:
- **`area_m2`:** Converted to numeric float/int. Ranges (e.g. `25 - 35`) averaged to `30.0`.
- **`electric_price`:** Standardized to VND/kWh. Ranges averaged (e.g. `2.000 - 4.000đ/Kwh` $\rightarrow$ `3000`), free/included set to `0`, state residential rate ("giá dân") standardized to official EVN residential average with VAT (`2500` VND/kWh).
- **`water_price`:** Standardized to numerical rates. Ranges averaged (e.g. `35.000 - 120.000đ/người` $\rightarrow$ `77500`), free set to `0`, state residential clean water rate ("giá dân") mapped to official Hanoi residential average with VAT and environmental fee (`12000` VND/m³).
- **`wifi_price` & `parking_fee` & `other_utilities_price`:** Normalized to clean integer amounts in VND. "Miễn phí" / free / included mapped to `0`. Ranges averaged to midpoints.
- **Amenity Flags (7 features):** All 7 boolean flags (`air_conditioner`, `water_heater`, `refrigerator`, `washing_machine`, `elevator`, `balcony_window`, `pet_allowed`) strictly encoded as binary `1` (True) and `0` (False). `fire_safety` dropped per specification.
- **Contact Details:** Retained only `contact_phone`; dropped extraneous contact fields (`contact_name`, `contact_zalo`).
- **Spatial Ward Resolution:** For listings with missing wards (particularly PhongTot and YourHome), coordinates (`latitude`, `longitude`) are matched against a comprehensive database of official Hanoi district ward centroids using Haversine spherical distance. Resolved 1,217 missing ward records.

---

## 5. Instructions for Re-running & Updating

To refresh any part of the data in the future:

1. **Update YourHome listings:**
   ```bash
   python3 /home/totallynotminh/Documents/FunDS/crawl_rooms.py --city ha-noi
   ```
2. **Update Rencity listings:**
   ```bash
   python3 /home/totallynotminh/Documents/FunDS/crawl_rencity.py
   ```
3. **Update PhongTot listings:**
   ```bash
   python3 /home/totallynotminh/Documents/FunDS/crawl_phongtot.py --pages 96
   ```
4. **Re-build the Unified Dataset:**
   ```bash
   python3 /home/totallynotminh/Documents/FunDS/build_unified_dataset.py
   ```
