"""Cleaning rules for the flat 31-column "sample" CSV schema.

That schema is sample.csv's (third-party PhongTot / Rencity / YourHome rows)
and the one src/export/*_to_sample.py writes (mogi_hanoi_extracted.csv,
alonhadat_hanoi_extracted.csv). It is not the canonical Parquet schema that
src/clean/run_clean.py cleans: there is no description column, sample.csv has
no raw HTML behind it to re-parse, and each of its sources lacks a basic field
(every PhongTot row has price 0, every Rencity row has no area). So these rules
flag problems rather than drop rows. The only rows a caller should remove are
the same-platform duplicates mark_duplicates identifies.

Pure functions of strings and DataFrames, no network. Rows flagged here as
lacking usable coordinates are geocoded separately.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from src.clean.outliers import flag_outliers
from src.clean.text_clean import ascii_fold, normalize_text
from src.crawl.pii import hash_value

SAMPLE_COLUMNS = [
    "platform", "listing_id", "title", "district", "ward", "address",
    "price_vnd", "house_type", "area_m2", "electric_price", "water_price",
    "wifi_price", "other_utilities_price", "parking_fee", "air_conditioner",
    "water_heater", "refrigerator", "washing_machine", "elevator",
    "balcony_window", "fire_safety", "pet_allowed", "amenities_list",
    "latitude", "longitude", "contact_name", "contact_phone", "contact_zalo",
    "image_count", "image_urls", "listing_url",
]
AMENITY_COLUMNS = [
    "air_conditioner", "water_heater", "refrigerator", "washing_machine",
    "elevator", "balcony_window", "fire_safety", "pet_allowed",
]
TEXT_COLUMNS = [
    "title", "address", "house_type", "electric_price", "water_price", "wifi_price",
    "other_utilities_price", "parking_fee", "amenities_list", "contact_name",
]
# Read these as text: pandas would otherwise parse "0917831531" as an int and
# drop the leading zero, which changes the phone hash.
READ_DTYPES = {c: str for c in ("listing_id", "district", "ward", "contact_phone", "contact_zalo")}

# Hanoi's 30 pre-2025 district-level units, as listed in alonhadat's own
# district <select> (tests/fixtures/alonhadat/detail_page_1.html, saved
# 2026-09-11). Listings still use these legacy labels (docs/PLAN.md Phase 3).
HANOI_DISTRICTS = (
    "Quận Ba Đình", "Quận Bắc Từ Liêm", "Quận Cầu Giấy", "Quận Đống Đa", "Quận Hà Đông",
    "Quận Hai Bà Trưng", "Quận Hoàn Kiếm", "Quận Hoàng Mai", "Quận Long Biên",
    "Quận Nam Từ Liêm", "Quận Tây Hồ", "Quận Thanh Xuân", "Thị xã Sơn Tây",
    "Huyện Ba Vì", "Huyện Chương Mỹ", "Huyện Đan Phượng", "Huyện Đông Anh", "Huyện Gia Lâm",
    "Huyện Hoài Đức", "Huyện Mê Linh", "Huyện Mỹ Đức", "Huyện Phú Xuyên", "Huyện Phúc Thọ",
    "Huyện Quốc Oai", "Huyện Sóc Sơn", "Huyện Thạch Thất", "Huyện Thanh Oai",
    "Huyện Thanh Trì", "Huyện Thường Tín", "Huyện Ứng Hòa",
)

# Hanoi spans roughly 20.56-21.39 N, 105.28-106.02 E; padded slightly. Every
# coordinate outside this box in these files is a placeholder, not a location:
# mogi's (10.77203, 106.69832) is central Ho Chi Minh City and
# (14.058324, 108.277199) the centre of Vietnam; Rencity's (85.0511, -180) is
# the corner of a Web Mercator map.
HANOI_LAT = (20.50, 21.45)
HANOI_LON = (105.25, 106.05)

PRICE_REL_TOL = 0.05   # same as src/clean/dedup.py's attribute match
AREA_ABS_TOL_M2 = 1.0

_DISTRICT_PREFIX_RE = re.compile(r"^(quan|huyen|thi xa|tx|q)\.?\s+")
_DISTRICT_IN_TEXT_RE = re.compile(r"\b(Quận|Huyện|Thị xã)\s+([^,]+)")
_WARD_IN_TEXT_RE = re.compile(r"\b(Phường|Xã|Thị trấn)\s+([^,]+)")
_WARD_PREFIX_RE = re.compile(r"^(Phường|Xã|Thị trấn)\s")
_HASH_RE = re.compile(r"[0-9a-f]{16}")


def _district_core(value: str) -> str:
    folded = re.sub(r"\s+", " ", ascii_fold(value).strip())
    return _DISTRICT_PREFIX_RE.sub("", folded)


_DISTRICT_BY_CORE = {_district_core(d): d for d in HANOI_DISTRICTS}


def _clean_str(value: object) -> str | None:
    """normalize_text for single-line CSV fields: also collapses newlines/double spaces."""
    if not isinstance(value, str):
        return None
    text = normalize_text(value)
    text = re.sub(r"\s+", " ", text).strip() if text else ""
    return text or None


def normalize_district(value: object) -> str | None:
    """Map "Đống Đa" / "quan dong da" / "Quận Đống Đa" to the canonical legacy label.

    Anything that isn't one of Hanoi's 30 units (including sample.csv's
    "Chưa rõ", i.e. "unknown") becomes None.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    return _DISTRICT_BY_CORE.get(_district_core(value))


def district_from_address(address: object) -> str | None:
    if not isinstance(address, str):
        return None
    for m in _DISTRICT_IN_TEXT_RE.finditer(address):
        district = normalize_district(f"{m.group(1)} {m.group(2)}")
        if district:
            return district
    return None


def clean_ward(ward: object, address: object, district: object) -> str | None:
    """Best available legacy ward label: from the address text, else the ward column.

    - mogi's ward column holds a breadcrumb label ("Cho thuê Nhà trọ Trần Phú"),
      never a ward, but its address always names one.
    - Rencity gives bare names ("Dịch Vọng"). Every commune-level unit of a quận
      is a phường, so those get the prefix; a huyện's could be a xã or a thị
      trấn, so they stay bare.
    - Values may use either scheme: legacy ("Thanh Xuân Bắc") or 2025, whose
      wards often reuse an old district's name ("Phường Thanh Xuân", "Phường Từ
      Liêm"). Both are kept as given.
    """
    if isinstance(address, str):
        m = _WARD_IN_TEXT_RE.search(address)
        if m:
            return f"{m.group(1)} {m.group(2).strip()}"
    ward = _clean_str(ward)
    if ward is None or ascii_fold(ward).startswith("cho thue"):
        return None
    if _WARD_PREFIX_RE.match(ward):
        return ward
    if isinstance(district, str) and district.startswith("Quận"):
        return f"Phường {ward}"
    return ward


def coordinate_issues(lat: pd.Series, lon: pd.Series) -> pd.Series:
    """None where the coordinate is usable, else "missing" or "outside_hanoi"."""
    lat = pd.to_numeric(lat, errors="coerce")
    lon = pd.to_numeric(lon, errors="coerce")
    missing = lat.isna() | lon.isna()
    inside = lat.between(*HANOI_LAT) & lon.between(*HANOI_LON)
    issue = pd.Series([None] * len(lat), index=lat.index, dtype=object)
    issue[~missing & ~inside] = "outside_hanoi"
    issue[missing] = "missing"
    return issue


def hash_contact(value: object) -> str | None:
    """Salted phone hash (src/crawl/pii.py), with the number normalized first.

    Normalizing before hashing is what makes the same phone hash identically
    across platforms: digits only, "+84" to a leading 0, and a 9-digit number
    that lost its leading zero (read as an int somewhere upstream) gets it back.
    A value that is already a 16-hex phone_hash (alonhadat's export) passes through.
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    text = str(value).strip()
    if _HASH_RE.fullmatch(text):
        return text
    digits = re.sub(r"\D", "", text)
    if digits.startswith("84") and len(digits) == 11:
        digits = "0" + digits[2:]
    elif len(digits) == 9 and not digits.startswith("0"):
        digits = "0" + digits
    if len(digits) < 9:
        return None
    return hash_value(digits)


_AREA_RANGE_RE = re.compile(
    r"^\s*(\d+(?:[.,]\d+)?)\s*(?:-|–|~|đến)\s*(\d+(?:[.,]\d+)?)\s*(?:m2|m²)?\s*$", re.I
)
_AREA_NUMBER_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(?:m2|m²)?\s*$", re.I)


def parse_area(value: object) -> tuple[float | None, float | None]:
    """(min, max) m² from a number or a range like PhongTot's "20 - 27"; (None, None) if unusable."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None, None
    if isinstance(value, (int, float, np.integer, np.floating)):
        return (float(value), float(value)) if value > 0 else (None, None)
    text = str(value)
    m = _AREA_RANGE_RE.match(text)
    if m:
        lo, hi = sorted(float(g.replace(",", ".")) for g in m.groups())
    else:
        m = _AREA_NUMBER_RE.match(text)
        if not m:
            return None, None
        lo = hi = float(m.group(1).replace(",", "."))
    return (lo, hi) if lo > 0 else (None, None)


def _to_bool(value: object) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "t", "1", "yes"}
    return False


def clean_sample_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize a flat-schema frame and add flag columns. Never drops rows.

    Pass all platforms at once: the price-per-m2 outlier bounds are computed
    across whatever rows the frame contains.
    """
    missing_cols = [c for c in SAMPLE_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"not the flat sample schema; missing columns: {missing_cols}")
    out = df.reset_index(drop=True).copy()

    for col in TEXT_COLUMNS:
        out[col] = out[col].map(_clean_str)
    out["house_type"] = out["house_type"].replace({"phong_tro": "Phòng trọ"})

    out["district_raw"] = out["district"]
    districts = [
        normalize_district(label) or district_from_address(address)
        for label, address in zip(out["district"], out["address"])
    ]
    out["district"] = pd.Series(districts, index=out.index, dtype=object)
    out["ward"] = [
        clean_ward(w, a, d) for w, a, d in zip(out["ward"], out["address"], out["district"])
    ]

    out["price_vnd"] = pd.to_numeric(out["price_vnd"], errors="coerce")
    out.loc[out["price_vnd"] <= 0, "price_vnd"] = np.nan
    bounds = [parse_area(v) for v in out["area_m2"]]
    out["area_m2_min"] = pd.to_numeric(pd.Series([lo for lo, _ in bounds], dtype=object), errors="coerce")
    out["area_m2_max"] = pd.to_numeric(pd.Series([hi for _, hi in bounds], dtype=object), errors="coerce")
    out["area_is_range"] = [lo is not None and lo != hi for lo, hi in bounds]
    # A range is summarized by its midpoint; the bounds stay in area_m2_min/max.
    out["area_m2"] = (out["area_m2_min"] + out["area_m2_max"]) / 2
    out["price_missing"] = out["price_vnd"].isna()
    out["area_missing"] = out["area_m2"].isna()
    flagged = flag_outliers(pd.DataFrame({
        "price_vnd_month": out["price_vnd"],
        "area_m2": out["area_m2"],
        "district": out["district"],
        "province": "Hà Nội",
    }))
    out["is_outlier"] = flagged["is_outlier"]
    out["outlier_reason"] = flagged["outlier_reason"]

    for col in AMENITY_COLUMNS:
        out[col] = out[col].map(_to_bool)
    out["image_count"] = pd.to_numeric(out["image_count"], errors="coerce").astype("Int64")
    for col in ("contact_phone", "contact_zalo"):
        out[col] = out[col].map(hash_contact)

    out["latitude_orig"] = out["latitude"]
    out["longitude_orig"] = out["longitude"]
    lat = pd.to_numeric(out["latitude"], errors="coerce")
    lon = pd.to_numeric(out["longitude"], errors="coerce")
    out["coord_issue"] = coordinate_issues(lat, lon)
    usable = out["coord_issue"].isna()
    out["latitude"] = lat.where(usable)
    out["longitude"] = lon.where(usable)
    # "listing": whatever the platform published. Its precision is unknown --
    # many mogi rows share one ward-level point (see src/clean/dedup.py).
    out["geo_source"] = pd.Series(np.where(usable, "listing", None), index=out.index, dtype=object)
    out["geo_confidence"] = out["geo_source"]
    out["geo_query"] = None
    return out


def _title_key(title: object) -> str:
    return re.sub(r"\s+", " ", ascii_fold(_clean_str(title) or "")).strip()


def _specific_address_key(address: object) -> str:
    """Normalized address, or "" when the part before the ward names no house/alley number.

    Street- or neighbourhood-level addresses are shared by many different rooms,
    so only addresses with a number can identify a listing. Checking just the
    part before the ward keeps "Phường Mỹ Đình 1" from counting as a number.
    """
    key = _title_key(address)
    street_part = re.split(r"\b(?:phuong|xa|thi tran|quan|huyen|thi xa)\b", key)[0]
    return key if re.search(r"\d", street_part) else ""


def _same_number(a: float, b: float, *, abs_tol: float = 0.0, rel_tol: float = 0.0) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return False
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b)))


def mark_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Add duplicate_of (the kept row's listing_id; None on kept rows) and n_duplicates.

    Two rows are duplicates when they come from the same platform and district,
    their price (within 5%) and area (within 1 m²) agree -- a value missing on
    both counts as agreeing -- and they share either a normalized title or a
    normalized address that names a house or alley number. Street- and
    neighbourhood-level addresses ("Phố Kim Mã, Quận Ba Đình"; mogi's "Yên Xá,
    Xã Tân Triều, ...", eight different rooms at one price) never match on
    their own. Groups
    are formed with complete linkage, as in src/clean/dedup.py, so a chain of
    near-matches can't merge rows that don't match each other. Within a group
    the row with the most filled fields is kept (earliest row on a tie).
    Cross-platform matches are left alone: they are separate adverts, and
    each platform's file should keep its own rows.
    """
    df = df.reset_index(drop=True)
    keys = pd.DataFrame({
        "platform": df["platform"].fillna(""),
        "district": df["district"].fillna(""),
        "title": df["title"].map(_title_key),
        "address": df["address"].map(_specific_address_key),
        "price": pd.to_numeric(df["price_vnd"], errors="coerce"),
        "area": pd.to_numeric(df["area_m2"], errors="coerce"),
    })
    rec = keys.to_dict("index")

    def match(i: int, j: int) -> bool:
        a, b = rec[i], rec[j]
        numbers_agree = _same_number(
            a["price"], b["price"], rel_tol=PRICE_REL_TOL
        ) and _same_number(a["area"], b["area"], abs_tol=AREA_ABS_TOL_M2)
        if not numbers_agree:
            return False
        if a["title"] and a["title"] == b["title"]:
            return True
        return bool(a["address"]) and a["address"] == b["address"]

    groups: dict[int, set[int]] = {i: {i} for i in df.index}
    for _, block in keys.groupby(["platform", "district"], sort=False):
        ids = list(block.index)
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                a, b = ids[x], ids[y]
                group_a, group_b = groups[a], groups[b]
                if group_a is group_b or not match(a, b):
                    continue
                if all(match(p, q) for p in group_a for q in group_b):
                    merged = group_a | group_b
                    for member in merged:
                        groups[member] = merged

    filled = df.notna().sum(axis=1)
    out = df.copy()
    keep_of = {i: max(g, key=lambda k: (filled[k], -k)) for i, g in groups.items()}
    out["duplicate_of"] = [
        None if keep_of[i] == i else df.at[keep_of[i], "listing_id"] for i in df.index
    ]
    out["n_duplicates"] = [len(groups[i]) - 1 for i in df.index]
    return out
