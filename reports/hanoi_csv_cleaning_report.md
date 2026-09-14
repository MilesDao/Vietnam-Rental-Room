# Hanoi CSV cleaning report

Run at: 2026-09-12T02:31:18.074457+00:00

Inputs (not modified): `mogi_hanoi_extracted.csv`, `alonhadat_hanoi_extracted.csv`, `sample.csv`

Outputs: `data/processed/hanoi_listings_clean.csv`, plus one `data/processed/<input>_clean.csv` per input. Built by `python -m src.clean.run_clean_hanoi_csv`; rules in `src/clean/sample_schema.py`, geocoding in `src/geo/`.

## Rows

| platform | rows in | duplicates removed | rows out | price missing | area missing | area was a range | outliers flagged |
|---|---|---|---|---|---|---|---|
| Alonhadat.vn | 69 | 1 | 68 | 0 | 0 | 0 | 2 |
| Mogi.vn | 1770 | 22 | 1748 | 17 | 0 | 0 | 20 |
| PhongTot.com | 1122 | 17 | 1105 | 1105 | 0 | 431 | 1 |
| Rencity.vn | 891 | 21 | 870 | 0 | 870 | 0 | 2 |
| YourHome.top | 95 | 11 | 84 | 0 | 0 | 0 | 0 |
| **total** | 3947 | 72 | 3875 | 1122 | 870 | 431 | 25 |

Outlier reasons (flagged, not removed): `price_per_m2_district_outlier` 16, `area_too_small` 9, `price_too_high` 3, `area_too_large` 2, `price_too_low` 2

## Coordinates

Rows out, by where their coordinate came from:

| platform | placeholder coords removed | listing | alley | street | ward | district | city | not_found | not_attempted |
|---|---|---|---|---|---|---|---|---|---|
| Alonhadat.vn | 0 | 0 | 2 | 60 | 6 | 0 | 0 | 0 | 0 |
| Mogi.vn | 4 | 1716 | 2 | 28 | 2 | 0 | 0 | 0 | 0 |
| PhongTot.com | 0 | 0 | 0 | 1080 | 5 | 20 | 0 | 0 | 0 |
| Rencity.vn | 13 | 765 | 24 | 59 | 21 | 1 | 0 | 0 | 0 |
| YourHome.top | 0 | 83 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| **total** | 17 | 2564 | 28 | 1228 | 34 | 21 | 0 | 0 | 0 |

- `listing`: published by the platform; precision unknown (many mogi rows share one ward-level point).
- `alley`: a point on the named ngõ off the named street.
- `street`: a point on the named street inside the old district's bounding box. On a long street it can be a kilometre or more from the room.
- `ward` / `district`: the centre of that ward's or old district's boundary (OpenStreetMap keeps pre-2025 units as historic boundaries).
- `city`: the centre of a province outside Hanoi, for a stray non-Hanoi listing.
- `not_found`: no query returned a matching place; latitude/longitude stay empty.
- `not_attempted`: geocoding was skipped or stopped before reaching this address.

Filter on `geo_confidence` before using coordinates for distances: `ward` and `district` points are area centres, not the room.

## Geocoding

- Requests sent this run: 15; answered from cache: 810.
- Cache: `data/external/nominatim_cache.sqlite`; a re-run only sends queries not in it.
- Service: the public Nominatim API, used under its usage policy (https://operations.osmfoundation.org/policies/nominatim/): at most 1 request/second, single thread, cached, identifying User-Agent. Queries contain street, alley, ward and district names only -- no house numbers, phone numbers or names.
- Coordinates and `geo_confidence` were also written into the original CSVs (`mogi_hanoi_extracted.csv`, `alonhadat_hanoi_extracted.csv`, `sample.csv`); each untouched original is kept beside it as `<name>.bak`.

**Attribution:** © OpenStreetMap contributors (data under ODbL), geocoded with Nominatim. Credit this wherever these coordinates are published.

## Rules applied

- Text fields: Unicode NFC, emoji and control characters removed, whitespace collapsed.
- `district`: mapped to one of Hanoi's 30 pre-2025 district-level units; anything else (e.g. "Chưa rõ") becomes empty. The original is kept in `district_raw`.
- `ward`: taken from the address when it names one (mogi's ward column held a breadcrumb label, not a ward). Bare names in a quận get "Phường". Legacy and 2025 ward names both occur.
- `price_vnd` of 0 or less becomes empty with `price_missing` true (every PhongTot row). Rows are kept.
- `area_m2`: ranges such as "20 - 27" become their midpoint, with `area_m2_min`, `area_m2_max` and `area_is_range`; unusable values become empty with `area_missing` true.
- Outliers are flagged in `is_outlier`/`outlier_reason`, never removed: price under 200k or over 100M VND, area under 5 or over 500 m², or price per m² outside 3×IQR for its district.
- `contact_phone` / `contact_zalo` hold the project's salted phone hash (`src/crawl/pii.py`), computed after normalizing the number. No raw phone number is written.
- Coordinates outside Hanoi are placeholders (central Ho Chi Minh City, the centre of Vietnam, a Web Mercator map corner) and are replaced; originals stay in `latitude_orig`/`longitude_orig`.
- Duplicates: same platform and district, price within 5% and area within 1 m², and the same title or the same address with a house/alley number. The row with the most filled fields is kept and `n_duplicates` counts what was folded into it. Matches across platforms are kept.
