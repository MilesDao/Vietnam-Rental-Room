# Scraping & Cleaning chotot.com (Hanoi)

How the `chotot_hanoi_cleaned.csv` dataset is structured, its contents, and the methodology used to clean it. This document mirrors the structure of the `alonhadat` scraping documentation, tailored to the Chợ Tốt rental rooms (phòng trọ) data in Hanoi.

## 1. Dataset Overview

- **Total listings:** 3733
- **Geographic Scope:** Hanoi (22 districts)
- **Top Districts by Volume:** Quận Hoàng Mai (773), Quận Đống Đa (417), Quận Cầu Giấy (383)
- **Category:** `Phòng trọ` (Rental rooms)
- **File:** `chotot_hanoi_cleaned.csv`

The dataset represents a snapshot of the rental market on Chợ Tốt. Unlike Alonhadat, Chợ Tốt data often contains detailed amenity flags and utility prices directly in the listings or extracted from the body text.

## 2. Field Mapping & Schema

The cleaned CSV contains 32 columns. Below is the mapping of the canonical fields and how they represent the listing:

| Field Name | Type | Description |
|---|---|---|
| `listing_id` | Integer | The native Chợ Tốt ID for the listing. |
| `title` | String | The listing title. |
| `district`, `ward`, `address` | String | Location details. `address` contains the street level information. |
| `price_vnd` | Integer | Monthly rental price in VND. |
| `house_type` | String | Always "Phòng trọ" for this scope. |
| `area_m2` | Float | Floor size in square meters. (1330 rows have missing area). |
| `electric_price`, `water_price`, `wifi_price`, `other_uti` | String | Extracted utility prices (e.g., "4k" for electricity, "27k" for water). Extracted via NLP/Regex from the body. |
| **Amenities** (Booleans) | Boolean | `parking`, `air_condi`, `water_he`, `refrigerat`, `washing`, `elevator`, `balcony`, `fire_safet`, `pet_allow`. |
| `amenities` | String | A comma-separated list of amenities found. |
| `latitude`, `longitude` | Float | Geographic coordinates provided by the Chợ Tốt platform. |
| `contact_name` | String | The poster's name. |
| `contact_phone` | Float | Phone number (heavily masked/cleaned). |
| `contact_zalo` | Boolean | Whether the contact has Zalo. |
| `image_co`, `image_u` | Int / String | Number of images and the JSON/Array string of image URLs. |
| `listing_ur` | String | Full URL to the original listing. |
| `body` | String | The raw description text authored by the poster. |

## 3. Data Cleaning & PII Handling

Similar to the strict PII rules established in the scraping architecture:
- **Phone Numbers:** The raw phone numbers are mostly stripped or hashed in this cleaned export (only 9 rows retain a valid float format, which suggests heavy scrubbing during the cleaning phase).
- **Utility & Amenity Extraction:** Unlike some sites where amenities are strictly structured, this dataset runs a secondary NLP/Regex pass over the `body` to extract values like `electric_price` and boolean flags for `air_condi`, `elevator`, etc.
- **Coordinates:** Unlike Alonhadat (which lacks coordinates), Chợ Tốt provides `latitude` and `longitude` natively, meaning Phase 4 geocoding is largely bypassed or used only as a fallback.

## 4. Known Limitations

- **Missing Values:** Floor size (`area_m2`) is missing for 1330 listings, meaning any price-per-m2 calculation will require dropping these rows or imputing.
- **Utility Formats:** `electric_price` and `water_price` are stored as raw strings (e.g., "4k", "27k") rather than normalized integers, requiring an additional cast before numerical analysis.
- **Platform Column:** The `platform` column is entirely empty (NaN) and can be dropped in downstream tasks.

