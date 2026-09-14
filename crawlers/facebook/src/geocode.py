"""Lightweight offline geocoder for Hà Nội rental posts.

Facebook posts rarely contain a clean, structured address, so street-level
geocoding (e.g. Nominatim) is both slow (rate-limited) and unreliable on this
free-form Vietnamese text. Instead we detect the administrative **district**
mentioned in a post (directly, or via a ward name) and attach that district's
**centroid** latitude/longitude. Precision is reported honestly via
``geo_precision`` ("district", or "city" for the coarse fallback, or "none").

Coordinates are approximate district centroids (WGS84), adequate for analysis
and mapping at district granularity — not exact addresses.
"""

from __future__ import annotations

from . import hanoi_locations as hl

# Approximate district centroids (lat, lon) for the 29 pre-2025 Hà Nội districts.
DISTRICT_CENTROIDS: dict[str, tuple[float, float]] = {
    "Ba Đình": (21.0344, 105.8145),
    "Bắc Từ Liêm": (21.0717, 105.7639),
    "Cầu Giấy": (21.0303, 105.7967),
    "Chương Mỹ": (20.9167, 105.6667),
    "Đan Phượng": (21.0847, 105.6669),
    "Đông Anh": (21.1389, 105.8500),
    "Đống Đa": (21.0182, 105.8289),
    "Gia Lâm": (21.0392, 105.9469),
    "Hà Đông": (20.9556, 105.7589),
    "Hai Bà Trưng": (21.0075, 105.8560),
    "Hoài Đức": (21.0333, 105.7000),
    "Hoàn Kiếm": (21.0287, 105.8524),
    "Hoàng Mai": (20.9758, 105.8567),
    "Long Biên": (21.0386, 105.8967),
    "Mê Linh": (21.1833, 105.7333),
    "Mỹ Đức": (20.6833, 105.7500),
    "Nam Từ Liêm": (21.0000, 105.7639),
    "Phú Xuyên": (20.7333, 105.9000),
    "Phúc Thọ": (21.1000, 105.5667),
    "Quốc Oai": (21.0167, 105.6167),
    "Sóc Sơn": (21.2500, 105.8500),
    "Sơn Tây": (21.1333, 105.5000),
    "Thạch Thất": (21.0167, 105.5667),
    "Thanh Oai": (20.8500, 105.7667),
    "Thanh Trì": (20.9500, 105.8500),
    "Thanh Xuân": (20.9958, 105.8047),
    "Thường Tín": (20.8667, 105.8667),
    "Tây Hồ": (21.0700, 105.8200),
    "Ứng Hòa": (20.7167, 105.7833),
}

# Coarse fallback: central Hà Nội (Hồ Hoàn Kiếm area).
HANOI_CENTROID = (21.0278, 105.8342)

# Pre-tokenized lookup keys (accent-free), longest first so multi-word names
# match before shorter ones.
_DISTRICT_KEYS = sorted(hl.DISTRICT_ALIASES.keys(), key=len, reverse=True)
# Only wards that unambiguously map to a single district are usable for geo.
_WARD_KEYS = sorted(hl.WARD_TO_DISTRICT.keys(), key=len, reverse=True)


def _contains(haystack: str, needle: str) -> bool:
    """Whole-token substring test on space-padded normalized strings."""
    return needle and f" {needle} " in f" {haystack} "


def detect_district(text: str | None) -> tuple[str | None, str | None]:
    """Detect (district, ward) from free-form Vietnamese post text.

    Strategy: a ward name is more specific, so try unambiguous wards first
    (each maps to exactly one district), then fall back to district names.
    Returns (district, ward) with either/both possibly ``None``.
    """
    norm = hl.normalize_place(text)
    if not norm:
        return None, None

    # 1) Unambiguous ward -> its district (most specific signal).
    for key in _WARD_KEYS:
        if _contains(norm, key):
            ward, district = hl.WARD_TO_DISTRICT[key]
            if district:
                return district, ward

    # 2) Direct district mention.
    for key in _DISTRICT_KEYS:
        if _contains(norm, key):
            return hl.DISTRICT_ALIASES[key], None

    return None, None


def geocode_text(text: str | None) -> dict:
    """Return geo fields for a post: district, ward, latitude, longitude,
    geo_precision. District centroid when detected; city centroid otherwise."""
    district, ward = detect_district(text)
    if district and district in DISTRICT_CENTROIDS:
        lat, lon = DISTRICT_CENTROIDS[district]
        precision = "district"
    else:
        lat, lon = HANOI_CENTROID
        precision = "city"
    return {
        "district": district,
        "ward": ward,
        "latitude": lat,
        "longitude": lon,
        "geo_precision": precision,
    }
