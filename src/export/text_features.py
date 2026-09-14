"""Regex-based amenity/utility-price extraction shared by the `*_to_sample.py` exporters.

This is a second, cruder amenity detector than `src/clean/amenities.py` --
keyword-substring matching over free text, no negation handling -- kept
separate because these exporters produce a flat, human-browsable CSV (see
each exporter's module docstring) rather than the canonical cleaning
pipeline's output. It used to be copy-pasted whole into every exporter file;
pulled out here so a change to the keyword lists or utility regexes only
has to happen once.
"""
from __future__ import annotations

import re

# Utilities extraction regexes -- match a keyword plus whatever price/amount
# text follows it, so the CSV cell keeps the original snippet instead of just
# a yes/no flag.
RE_ELEC = re.compile(r"(?i)(điện\s*[:\s]*\d+[\.,]?\d*\s*k?(?:/số|/kw)?|điện\s*giá\s*dân)")
RE_WATER = re.compile(r"(?i)(nước\s*[:\s]*\d+[\.,]?\d*\s*k?(?:/người|/khối|/tháng)?|nước\s*giá\s*dân)")
RE_WIFI = re.compile(r"(?i)(wifi|internet|mạng)\s*[:\s]*(\d+[\.,]?\d*\s*k?(?:/phòng|/tháng|/người)?|miễn\s*phí|free)")
RE_PARKING = re.compile(r"(?i)(để\s*xe|gửi\s*xe|xe\s*máy)\s*[:\s]*(\d+[\.,]?\d*\s*k?(?:/xe|/tháng)?|miễn\s*phí|free)")
RE_SERVICE = re.compile(r"(?i)(phí\s*dịch\s*vụ|dịch\s*vụ|vệ\s*sinh)\s*[:\s]*(\d+[\.,]?\d*\s*k?(?:/người|/phòng|/tháng)?|miễn\s*phí|free)")

_AMENITY_KEYWORDS: dict[str, list[str]] = {
    "air_conditioner": ["điều hòa", "máy lạnh", "dieu hoa", "may lanh"],
    "water_heater": ["nóng lạnh", "nong lanh", "bình nóng", "máy nước nóng"],
    "refrigerator": ["tủ lạnh", "tu lanh"],
    "washing_machine": ["máy giặt", "may giat"],
    "elevator": ["thang máy", "thang may"],
    "balcony_window": ["ban công", "ban cong", "cửa sổ", "cua so"],
    "fire_safety": ["pccc", "thoát hiểm", "chữa cháy", "cứu hỏa", "phòng cháy"],
    "pet_allowed": ["thú cưng", "chó mèo", "pet"],
}

_AMENITY_LABELS: dict[str, str] = {
    "air_conditioner": "Điều hòa",
    "water_heater": "Nóng lạnh",
    "refrigerator": "Tủ lạnh",
    "washing_machine": "Máy giặt",
    "elevator": "Thang máy",
    "balcony_window": "Ban công/Cửa sổ",
    "fire_safety": "PCCC",
    "pet_allowed": "Thú cưng",
}


def has_keyword(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


def extract_amenity_features(text: str) -> dict[str, bool]:
    """One bool per amenity in `_AMENITY_KEYWORDS`, keyword-substring match over `text`."""
    return {key: has_keyword(text, kws) for key, kws in _AMENITY_KEYWORDS.items()}


def get_amenities_list(features: dict[str, bool]) -> str:
    """"; "-joined human labels for every truthy amenity in `features`."""
    return "; ".join(
        _AMENITY_LABELS[key] for key, value in features.items() if value and key in _AMENITY_LABELS
    )


def extract_utility_prices(text: str) -> dict[str, str]:
    """electric/water/wifi/parking/other-service price snippets found in `text`.

    Each value is the matched snippet as written (e.g. "điện 3.5k/số"), or ""
    if that utility wasn't mentioned -- not a parsed number, since the point
    of this CSV is a human-browsable spot-check, not a modeling feature.
    """
    matches = {
        "electric_price": RE_ELEC.search(text),
        "water_price": RE_WATER.search(text),
        "wifi_price": RE_WIFI.search(text),
        "parking_fee": RE_PARKING.search(text),
        "other_utilities_price": RE_SERVICE.search(text),
    }
    return {key: (m.group(0).strip() if m else "") for key, m in matches.items()}
