"""Deterministic validation and serialization for rental listing rows."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .hanoi_locations import normalize_place, resolve_hanoi_district

OUTPUT_COLUMNS = [
    "listing_id", "source", "url", "title", "description",
    "price_vnd_month", "area_m2", "address_raw", "city", "district",
    "ward", "house_type", "electric_price", "water_price", "wifi_price",
    "other_utilities_price", "parking_fee", "air_conditioner",
    "water_heater", "refrigerator", "washing_machine", "elevator",
    "balcony_window", "fire_safety", "pet_allowed", "room_type",
    "posted_at_raw", "phone_hash", "image_urls", "n_images", "crawled_at",
]

ALLOWED_CLASSIFICATIONS = {
    "rental_offer",
    "room_seeking",
    "property_sale",
    "recruitment",
    "warning_or_review",
    "general_information",
    "unrelated",
}

HOUSE_TYPES = {
    "Studio khép kín",
    "1 Phòng Ngủ (1PN/1N1K)",
    "2 Phòng Ngủ (2PN/2N1K)",
    "Gác xép / Duplex",
    "Chung cư mini (CCMN)",
    "Nhà nguyên căn",
    "Phòng trọ WC chung",
    "Phòng trọ khép kín",
}

HOUSE_TYPE_ALIASES = {
    "studio": "Studio khép kín",
    "studio khep kin": "Studio khép kín",
    "1pn": "1 Phòng Ngủ (1PN/1N1K)",
    "1n1k": "1 Phòng Ngủ (1PN/1N1K)",
    "1 phong ngu": "1 Phòng Ngủ (1PN/1N1K)",
    "2pn": "2 Phòng Ngủ (2PN/2N1K)",
    "2n1k": "2 Phòng Ngủ (2PN/2N1K)",
    "2 phong ngu": "2 Phòng Ngủ (2PN/2N1K)",
    "gac xep": "Gác xép / Duplex",
    "duplex": "Gác xép / Duplex",
    "ccmn": "Chung cư mini (CCMN)",
    "chung cu mini": "Chung cư mini (CCMN)",
    "nha nguyen can": "Nhà nguyên căn",
    "phong tro wc chung": "Phòng trọ WC chung",
    "phong tro khep kin": "Phòng trọ khép kín",
}

HOUSE_TYPE_SOURCE_PATTERNS = {
    "Studio khép kín": (r"\bstudio\b",),
    "1 Phòng Ngủ (1PN/1N1K)": (
        r"\b1pn\b", r"\b1n1k\b", r"\b1 phong ngu\b", r"\b1 ngu\b",
    ),
    "2 Phòng Ngủ (2PN/2N1K)": (
        r"\b2pn\b", r"\b2n1k\b", r"\b2 phong ngu\b", r"\b2 ngu\b",
    ),
    "Gác xép / Duplex": (r"\bgac(?: xep)?\b", r"\bduplex\b"),
    "Chung cư mini (CCMN)": (r"\bccmn\b", r"\bchung cu mini\b"),
    "Nhà nguyên căn": (r"\bnha nguyen can\b", r"\bnguyen can\b"),
    "Phòng trọ WC chung": (
        r"\bwc chung\b", r"\bve sinh chung\b", r"\bnvs chung\b",
    ),
    "Phòng trọ khép kín": (
        r"\bkhep kin\b", r"\bvskk\b", r"\bwc rieng\b", r"\bvs rieng\b",
    ),
}

AMENITY_FIELDS = (
    "air_conditioner",
    "water_heater",
    "refrigerator",
    "washing_machine",
    "elevator",
    "balcony_window",
    "fire_safety",
    "pet_allowed",
)

UTILITY_FIELDS = (
    "electric_price",
    "water_price",
    "wifi_price",
    "other_utilities_price",
    "parking_fee",
)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    option_index: int | None = None


@dataclass
class ValidationResult:
    classification: str
    skip_reason: str | None
    listings: list[dict[str, Any]] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)


def _accentless(value: str) -> str:
    text = unicodedata.normalize("NFD", value.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn").replace(
        "đ", "d"
    )


def normalize_rent_price(value: object) -> int | None:
    """Normalize a supported monthly rent expression to integer VND."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        amount = int(value)
        return amount if 300_000 <= amount <= 100_000_000 else None

    raw = str(value).strip().lower()
    if not raw or "xx" in raw:
        return None
    if re.search(r"/(?:\s*)(?:so|số|khoi|khối|m3|m³|nguoi|người)", raw):
        return None

    text = re.sub(r"\s+", " ", raw)
    range_match = re.search(
        r"(\d{1,2}(?:[,.]\d{1,3})?)\s*(?:tr(?:ieu)?|triệu)?\s*[-–—]\s*"
        r"\d{1,2}(?:[,.]\d{1,3})?\s*(?:tr(?:ieu)?|triệu)\b",
        text,
    )
    if range_match:
        lower = float(range_match.group(1).replace(",", "."))
        return round(lower * 1_000_000)
    match = re.search(r"(\d{1,2})\s*tr\s*(\d{1,3})(?!\d)", text)
    if match:
        whole, fraction = match.groups()
        amount = int(whole) * 1_000_000 + round(
            int(fraction) * 1_000_000 / (10 ** len(fraction))
        )
        return amount if amount <= 100_000_000 else None

    match = re.search(r"(\d{1,2})[,.](\d{1,3})\s*(?:tr(?:ieu)?|triệu)\b", text)
    if match:
        whole, fraction = match.groups()
        return int(whole) * 1_000_000 + round(
            int(fraction) * 1_000_000 / (10 ** len(fraction))
        )

    match = re.search(r"(\d{1,2})\s*(?:tr(?:ieu)?|triệu)\b", text)
    if match:
        return int(match.group(1)) * 1_000_000

    match = re.search(r"(\d{1,3}(?:[.,]\d{3})+)\s*k\b", text)
    if match:
        amount = int(re.sub(r"[.,]", "", match.group(1))) * 1_000
        return amount if 300_000 <= amount <= 100_000_000 else None

    match = re.search(r"(\d+(?:[.,]\d+)?)\s*k\b", text)
    if match:
        amount = int(float(match.group(1).replace(",", ".")) * 1_000)
        return amount if 300_000 <= amount <= 100_000_000 else None

    digits = re.sub(r"[^0-9]", "", text)
    if digits and re.fullmatch(
        r"[\d.,]+\s*(?:đ|vnd)?\s*(?:/tháng|/thang)?", text
    ):
        amount = int(digits)
        return amount if 300_000 <= amount <= 100_000_000 else None
    return None


def extract_rent_prices(value: object) -> list[int]:
    """Return every explicit plausible rent amount found in a text fragment."""
    if value is None:
        return []
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        normalized = normalize_rent_price(value)
        return [normalized] if normalized is not None else []

    text = _accentless(str(value))
    found: list[tuple[int, int, tuple[int, int]]] = []

    def add_matches(pattern: str, converter) -> None:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            span = match.span()
            if any(not (span[1] <= used[0] or span[0] >= used[1]) for _, _, used in found):
                continue
            amount = converter(match)
            if 300_000 <= amount <= 100_000_000:
                found.append((span[0], amount, span))

    add_matches(
        r"(?<![a-z0-9])(\d{1,3}(?:[.,]\d{3}){2})(?!\d)",
        lambda m: int(re.sub(r"[.,]", "", m.group(1))),
    )
    add_matches(
        r"(?<![a-z0-9])(\d{1,2})tr(\d{1,3})(?!\d)",
        lambda m: int(m.group(1)) * 1_000_000
        + round(int(m.group(2)) * 1_000_000 / (10 ** len(m.group(2)))),
    )
    add_matches(
        r"(?<![a-z0-9])(\d)(?:t|m|r)(\d{1,3})(?!\d)",
        lambda m: int(m.group(1)) * 1_000_000
        + round(int(m.group(2)) * 1_000_000 / (10 ** len(m.group(2)))),
    )
    add_matches(
        r"(?<![a-z0-9])(\d{1,2})[,.](\d{1,3})\s*(?:tr(?:ieu)?)\b",
        lambda m: int(m.group(1)) * 1_000_000
        + round(int(m.group(2)) * 1_000_000 / (10 ** len(m.group(2)))),
    )
    # In a price range the unit is often written only on the last value:
    # ``2,4-3tr`` or ``2,6 _2,8-3tr``.
    if re.search(r"\d\s*(?:tr(?:ieu)?)\b", text):
        add_matches(
            r"(?<![a-z0-9])(\d{1,2})[,.](\d{1,3})(?![a-z0-9])",
            lambda m: int(m.group(1)) * 1_000_000
            + round(int(m.group(2)) * 1_000_000 / (10 ** len(m.group(2)))),
        )
    add_matches(
        r"(?<![a-z0-9])(\d{1,2})\s*(?:tr(?:ieu)?)\b",
        lambda m: int(m.group(1)) * 1_000_000,
    )
    add_matches(
        r"(?<![a-z0-9])(\d{1,3}(?:[.,]\d{3})+)\s*k\b",
        lambda m: int(re.sub(r"[.,]", "", m.group(1))) * 1_000,
    )
    add_matches(
        r"(?<![a-z0-9])(\d+(?:[.,]\d+)?)\s*k\b",
        lambda m: round(float(m.group(1).replace(",", ".")) * 1_000),
    )
    add_matches(
        r"(?<![a-z0-9])(\d{6,9})(?!\d)",
        lambda m: int(m.group(1)),
    )

    found.sort(key=lambda item: item[0])
    ordered: list[int] = []
    for _, amount, _ in found:
        if amount not in ordered:
            ordered.append(amount)
    return ordered


def normalize_utility_value(value: object) -> str | None:
    """Normalize a utility fee while preserving its charging denominator."""
    if value is None:
        return None
    raw = re.sub(r"\s+", " ", str(value)).strip()
    if not raw:
        return None
    key = _accentless(raw)
    if key == "free" or "mien phi" in key:
        return "Miễn phí"
    if "da gom" in key or "da bao gom" in key or "included" in key:
        return "Đã bao gồm"
    if "dien gia dan" in key or "gia nha nuoc" in key:
        return "Điện giá dân"

    text = raw.lower()
    text = re.sub(r"\s*/\s*", "/", text)
    text = re.sub(r"\s*(?:đ|vnd)\s*", "", text)
    text = re.sub(r"/(?:m3|m³)\b", "/khối", text)
    text = re.sub(r"/1\s*", "/", text)

    def thousands(match: re.Match[str]) -> str:
        number = int(re.sub(r"[.,]", "", match.group(1)))
        return f"{number // 1000}k" if number % 1000 == 0 else str(number)

    text = re.sub(r"\b(\d{1,3}(?:[.,]\d{3})+)\b", thousands, text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*/", "/", text)
    return text or None


def hash_phones(text: str) -> str | None:
    """Hash the deterministic set of Vietnamese phone numbers in text."""
    candidates = re.findall(r"(?:\+?84|0)(?:[\s.()-]*\d){9}", text or "")
    normalized: set[str] = set()
    for candidate in candidates:
        digits = re.sub(r"\D", "", candidate)
        if digits.startswith("84") and len(digits) == 11:
            digits = "0" + digits[2:]
        if len(digits) == 10 and digits.startswith("0"):
            normalized.add(digits)
    if not normalized:
        return None
    joined = "|".join(sorted(normalized))
    return hashlib.sha256(joined.encode("ascii")).hexdigest()


def canonical_house_type(value: object) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if raw in HOUSE_TYPES:
        return raw
    return HOUSE_TYPE_ALIASES.get(normalize_place(raw))


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        number = float(str(value).replace(",", "."))
    except ValueError:
        return None
    return number if 0 < number <= 1_000 else None


def _clean_scalar(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _evidence_in_source(
    value: object, source_text: str, *, allow_fragments: bool = False
) -> bool:
    """Require a non-empty literal evidence fragment in normalized source text."""
    evidence = _clean_scalar(value)
    if not evidence:
        return False
    source_key = normalize_place(source_text)
    if normalize_place(evidence) in source_key:
        return True
    if not allow_fragments:
        return False
    fragments = [part.strip() for part in re.split(r"[;,]", evidence) if part.strip()]
    return len(fragments) > 1 and all(
        normalize_place(fragment) in source_key for fragment in fragments
    )


def _evidence_failure(
    issues: list[ValidationIssue], option_index: int, field_group: str
) -> None:
    issues.append(
        ValidationIssue(
            "unsupported_evidence",
            f"{field_group} evidence is missing from the source post",
            option_index,
        )
    )


def _house_type_supported(house_type: str, source_text: str) -> bool:
    """Check canonical house types against explicit source terminology."""
    source_key = normalize_place(source_text)
    return any(
        re.search(pattern, source_key)
        for pattern in HOUSE_TYPE_SOURCE_PATTERNS.get(house_type, ())
    )


def _normalize_listing(
    option: dict[str, Any],
    option_index: int,
    issues: list[ValidationIssue],
    source_text: str | None = None,
) -> dict[str, Any] | None:
    price = normalize_rent_price(option.get("price_vnd_month"))
    if price is None:
        issues.append(
            ValidationIssue(
                "invalid_price",
                "Rental option has no supported monthly VND price",
                option_index,
            )
        )
        return None

    result: dict[str, Any] = {
        "source_order": option.get("source_order", option_index + 1),
        "room_id": _clean_scalar(option.get("room_id")),
        "title": _clean_scalar(option.get("title")),
        "price_vnd_month": price,
        "area_m2": _number(option.get("area_m2")),
        "address_raw": _clean_scalar(option.get("address_raw")),
        "city": "hanoi" if normalize_place(_clean_scalar(option.get("city"))) in {"hanoi", "ha noi"} else None,
        "district": _clean_scalar(option.get("district")),
        "ward": _clean_scalar(option.get("ward")),
        "house_type": canonical_house_type(option.get("house_type")),
        "room_type": _clean_scalar(option.get("room_type")) or "phòng trọ",
    }
    for utility in UTILITY_FIELDS:
        result[utility] = normalize_utility_value(option.get(utility))
    for amenity in AMENITY_FIELDS:
        value = option.get(amenity, False)
        if not isinstance(value, bool):
            issues.append(
                ValidationIssue(
                    "invalid_boolean",
                    f"{amenity} must be a JSON boolean",
                    option_index,
                )
            )
            value = False
        result[amenity] = value

    if source_text is not None:
        evidence = option.get("evidence")
        if not isinstance(evidence, dict):
            _evidence_failure(issues, option_index, "price")
            return None
        price_evidence = evidence.get("price")
        if (
            not _evidence_in_source(price_evidence, source_text)
            or result["price_vnd_month"] not in extract_rent_prices(price_evidence)
        ):
            _evidence_failure(issues, option_index, "price")
            return None
        checks = [
            (
                bool(result.get("house_type")),
                "house_type",
                evidence.get("house_type"),
            ),
            (
                any(
                    result.get(name)
                    for name in ("address_raw", "district", "ward", "city")
                ),
                "location",
                evidence.get("location"),
            ),
            (result.get("area_m2") is not None, "area", evidence.get("area")),
            (
                any(result.get(name) for name in UTILITY_FIELDS),
                "utilities",
                evidence.get("utilities"),
            ),
            (
                any(result.get(name) is True for name in AMENITY_FIELDS),
                "amenities",
                evidence.get("amenities"),
            ),
        ]
        for required, field_group, fragment in checks:
            supported = _evidence_in_source(
                fragment,
                source_text,
                allow_fragments=field_group in {"location", "utilities", "amenities"},
            )
            if field_group == "house_type" and result.get("house_type"):
                supported = supported or _house_type_supported(
                    result["house_type"], source_text
                )
            if required and not supported:
                _evidence_failure(issues, option_index, field_group)
                if field_group == "house_type":
                    result["house_type"] = None
                elif field_group == "location":
                    for name in ("address_raw", "district", "ward", "city"):
                        result[name] = None
                elif field_group == "area":
                    result["area_m2"] = None
                elif field_group == "utilities":
                    for name in UTILITY_FIELDS:
                        result[name] = None
                elif field_group == "amenities":
                    for name in AMENITY_FIELDS:
                        result[name] = False
    return result


def validate_response(payload: object, source_text: str) -> ValidationResult:
    """Validate untrusted model JSON and normalize accepted rental options."""
    if not isinstance(payload, dict):
        return ValidationResult(
            "invalid",
            None,
            issues=[ValidationIssue("invalid_payload", "Response must be a JSON object")],
        )

    classification = payload.get("classification")
    skip_reason = _clean_scalar(payload.get("skip_reason"))
    if classification not in ALLOWED_CLASSIFICATIONS:
        return ValidationResult(
            "invalid",
            skip_reason,
            issues=[
                ValidationIssue(
                    "invalid_classification",
                    f"Unsupported classification: {classification!r}",
                )
            ],
        )

    raw_listings = payload.get("listings", [])
    if not isinstance(raw_listings, list):
        return ValidationResult(
            "invalid",
            skip_reason,
            issues=[ValidationIssue("invalid_listings", "listings must be a JSON array")],
        )

    issues: list[ValidationIssue] = []
    if classification != "rental_offer":
        if raw_listings:
            issues.append(
                ValidationIssue(
                    "non_rental_listings_ignored",
                    "Listings were ignored because classification is not rental_offer",
                )
            )
        return ValidationResult(classification, skip_reason, [], issues)

    listings: list[dict[str, Any]] = []
    for index, option in enumerate(raw_listings):
        if not isinstance(option, dict):
            issues.append(
                ValidationIssue("invalid_option", "Listing option must be an object", index)
            )
            continue
        normalized = _normalize_listing(option, index, issues, source_text)
        if normalized is not None:
            listings.append(normalized)
    return ValidationResult(classification, skip_reason, listings, issues)


def _source_identity(source: dict[str, str]) -> str:
    post_id = _clean_scalar(source.get("post_id"))
    if post_id:
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "", post_id)
        if safe_id:
            return safe_id
    basis = json.dumps(
        {"post_url": source.get("post_url", ""), "text": source.get("text", "")},
        ensure_ascii=False,
        sort_keys=True,
    )
    return "hash_" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _parse_images(value: object) -> list[str]:
    if isinstance(value, list):
        raw = value
    elif isinstance(value, str):
        try:
            raw = json.loads(value)
        except json.JSONDecodeError:
            raw = []
    else:
        raw = []
    return list(dict.fromkeys(item for item in raw if isinstance(item, str) and item))


def _dedupe_key(option: dict[str, Any]) -> tuple[Any, ...]:
    return (
        normalize_place(option.get("address_raw")),
        option.get("house_type"),
        option.get("price_vnd_month"),
        option.get("area_m2"),
        normalize_place(option.get("room_id")),
    )


def build_rows(source: dict[str, str], listings: list[dict]) -> list[dict]:
    """Build exact target-schema rows in deterministic order."""
    normalized: list[dict[str, Any]] = []
    issues: list[ValidationIssue] = []
    for index, option in enumerate(listings):
        item = _normalize_listing(option, index, issues)
        if item is not None:
            normalized.append(item)

    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for option in normalized:
        unique.setdefault(_dedupe_key(option), option)
    options = sorted(
        unique.values(),
        key=lambda option: (
            normalize_place(option.get("address_raw")),
            option.get("price_vnd_month") or 0,
            option.get("house_type") or "",
            option.get("area_m2") or 0,
            normalize_place(option.get("room_id")),
        ),
    )

    images = _parse_images(source.get("image_urls"))
    identity = _source_identity(source)
    rows: list[dict[str, Any]] = []
    for index, option in enumerate(options, 1):
        district, ward = resolve_hanoi_district(
            option.get("district"), option.get("ward")
        )
        house_type = option.get("house_type")
        title = option.get("title") or " - ".join(
            part
            for part in (
                house_type or "Phòng cho thuê",
                option.get("address_raw"),
                f"{option['price_vnd_month']:,} VND/tháng".replace(",", "."),
            )
            if part
        )
        row: dict[str, Any] = {column: None for column in OUTPUT_COLUMNS}
        row.update(
            {
                "listing_id": f"facebook_{identity}_{index:03d}",
                "source": "facebook",
                "url": _clean_scalar(source.get("post_url")),
                "title": title,
                "description": source.get("text") or "",
                "price_vnd_month": option["price_vnd_month"],
                "area_m2": option.get("area_m2"),
                "address_raw": option.get("address_raw"),
                "city": option.get("city"),
                "district": district,
                "ward": ward,
                "house_type": house_type,
                "room_type": option.get("room_type") or "phòng trọ",
                "posted_at_raw": _clean_scalar(source.get("timestamp"))
                or _clean_scalar(source.get("timestamp_text")),
                "phone_hash": hash_phones(source.get("text") or ""),
                "image_urls": json.dumps(images, ensure_ascii=False),
                "n_images": len(images),
                "crawled_at": _clean_scalar(source.get("crawl_time")),
            }
        )
        for name in UTILITY_FIELDS + AMENITY_FIELDS:
            row[name] = option.get(name)
        rows.append(row)
    return rows


def write_output_csv(path: Path, rows: Iterable[dict]) -> int:
    """Write normalized rows with the exact reference column order."""
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS, extrasaction="raise")
        writer.writeheader()
        writer.writerows(materialized)
    return len(materialized)
