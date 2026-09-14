"""Canonical Hanoi locations used by rental-listing normalization.

Facebook posts commonly use the pre-2025 ward vocabulary, so this module
keeps those names as stable analytical labels rather than attempting to infer
new administrative boundaries from incomplete post text.
"""

from __future__ import annotations

import re
import unicodedata


def normalize_place(value: str | None) -> str:
    """Return a lowercase, accent-free lookup key for a Vietnamese place."""
    if not value:
        return ""
    text = unicodedata.normalize("NFD", str(value).lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("đ", "d")
    text = re.sub(r"\b(?:quan|huyen|thi xa|phuong|xa|thi tran)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


_DISTRICTS = (
    "Ba Đình", "Bắc Từ Liêm", "Cầu Giấy", "Chương Mỹ", "Đan Phượng",
    "Đông Anh", "Đống Đa", "Gia Lâm", "Hà Đông", "Hai Bà Trưng",
    "Hoài Đức", "Hoàn Kiếm", "Hoàng Mai", "Long Biên", "Mê Linh",
    "Mỹ Đức", "Nam Từ Liêm", "Phú Xuyên", "Phúc Thọ", "Quốc Oai",
    "Sóc Sơn", "Sơn Tây", "Thạch Thất", "Thanh Oai", "Thanh Trì",
    "Thanh Xuân", "Thường Tín", "Tây Hồ", "Ứng Hòa",
)

DISTRICT_ALIASES = {normalize_place(name): name for name in _DISTRICTS}

_DISTRICT_WARDS: dict[str, tuple[str, ...]] = {
    "Ba Đình": (
        "Cống Vị", "Điện Biên", "Đội Cấn", "Giảng Võ", "Kim Mã",
        "Liễu Giai", "Ngọc Hà", "Ngọc Khánh", "Nguyễn Trung Trực",
        "Phúc Xá", "Quán Thánh", "Thành Công", "Trúc Bạch", "Vĩnh Phúc",
    ),
    "Hoàn Kiếm": (
        "Chương Dương", "Cửa Đông", "Cửa Nam", "Đồng Xuân", "Hàng Bạc",
        "Hàng Bài", "Hàng Bồ", "Hàng Bông", "Hàng Buồm", "Hàng Đào",
        "Hàng Gai", "Hàng Mã", "Hàng Trống", "Lý Thái Tổ",
        "Phan Chu Trinh", "Phúc Tân", "Trần Hưng Đạo", "Tràng Tiền",
    ),
    "Tây Hồ": (
        "Bưởi", "Nhật Tân", "Phú Thượng", "Quảng An", "Thụy Khuê",
        "Tứ Liên", "Xuân La", "Yên Phụ",
    ),
    "Long Biên": (
        "Bồ Đề", "Cự Khối", "Đức Giang", "Gia Thụy", "Giang Biên",
        "Long Biên", "Ngọc Lâm", "Ngọc Thụy", "Phúc Đồng", "Phúc Lợi",
        "Sài Đồng", "Thạch Bàn", "Thượng Thanh", "Việt Hưng",
    ),
    "Cầu Giấy": (
        "Dịch Vọng", "Dịch Vọng Hậu", "Mai Dịch", "Nghĩa Đô",
        "Nghĩa Tân", "Quan Hoa", "Trung Hòa", "Yên Hòa",
    ),
    "Đống Đa": (
        "Cát Linh", "Hàng Bột", "Khâm Thiên", "Khương Thượng", "Kim Liên",
        "Láng Hạ", "Láng Thượng", "Nam Đồng", "Ngã Tư Sở", "Ô Chợ Dừa",
        "Phương Liên", "Phương Mai", "Quang Trung", "Quốc Tử Giám",
        "Thịnh Quang", "Thổ Quan", "Trung Liệt", "Trung Phụng",
        "Trung Tự", "Văn Chương", "Văn Miếu",
    ),
    "Hai Bà Trưng": (
        "Bạch Đằng", "Bách Khoa", "Bạch Mai", "Cầu Dền", "Đống Mác",
        "Đồng Nhân", "Đồng Tâm", "Lê Đại Hành", "Minh Khai",
        "Ngô Thì Nhậm", "Nguyễn Du", "Phạm Đình Hổ", "Phố Huế",
        "Quỳnh Lôi", "Quỳnh Mai", "Thanh Lương", "Thanh Nhàn",
        "Trương Định", "Vĩnh Tuy",
    ),
    "Hoàng Mai": (
        "Đại Kim", "Định Công", "Giáp Bát", "Hoàng Liệt",
        "Hoàng Văn Thụ", "Lĩnh Nam", "Mai Động", "Tân Mai", "Thanh Trì",
        "Thịnh Liệt", "Trần Phú", "Tương Mai", "Vĩnh Hưng", "Yên Sở",
    ),
    "Thanh Xuân": (
        "Hạ Đình", "Khương Đình", "Khương Mai", "Khương Trung", "Kim Giang",
        "Nhân Chính", "Phương Liệt", "Thanh Xuân Bắc", "Thanh Xuân Nam",
        "Thanh Xuân Trung", "Thượng Đình",
    ),
    "Hà Đông": (
        "Biên Giang", "Dương Nội", "Đồng Mai", "Hà Cầu", "Kiến Hưng",
        "La Khê", "Mộ Lao", "Nguyễn Trãi", "Phú La", "Phú Lãm",
        "Phú Lương", "Phúc La", "Quang Trung", "Vạn Phúc", "Văn Quán",
        "Yên Nghĩa", "Yết Kiêu",
    ),
    "Bắc Từ Liêm": (
        "Cổ Nhuế 1", "Cổ Nhuế 2", "Đông Ngạc", "Đức Thắng", "Liên Mạc",
        "Minh Khai", "Phú Diễn", "Phúc Diễn", "Tây Tựu", "Thượng Cát",
        "Thụy Phương", "Xuân Đỉnh", "Xuân Tảo",
    ),
    "Nam Từ Liêm": (
        "Cầu Diễn", "Đại Mỗ", "Mễ Trì", "Mỹ Đình 1", "Mỹ Đình 2",
        "Phú Đô", "Phương Canh", "Tây Mỗ", "Trung Văn", "Xuân Phương",
    ),
}

WARD_CANDIDATES: dict[str, list[tuple[str, str]]] = {}
for _district, _wards in _DISTRICT_WARDS.items():
    for _ward in _wards:
        WARD_CANDIDATES.setdefault(normalize_place(_ward), []).append(
            (_ward, _district)
        )

# Common area label whose numbered wards are not distinguished in posts.
WARD_CANDIDATES["co nhue"] = [("Cổ Nhuế", "Bắc Từ Liêm")]

WARD_TO_DISTRICT = {
    key: candidates[0]
    for key, candidates in WARD_CANDIDATES.items()
    if len(candidates) == 1
}


def canonical_district(value: str | None) -> str | None:
    """Map district names and URL slugs to their canonical label."""
    return DISTRICT_ALIASES.get(normalize_place(value))


def resolve_hanoi_district(
    district: str | None,
    ward: str | None,
) -> tuple[str | None, str | None]:
    """Resolve a compatible district/ward pair without choosing ambiguities."""
    explicit = canonical_district(district)
    candidates = WARD_CANDIDATES.get(normalize_place(ward), [])

    if explicit and candidates:
        matches = [candidate for candidate in candidates if candidate[1] == explicit]
        if matches:
            return explicit, matches[0][0]
        return None, candidates[0][0]

    if not explicit and len(candidates) > 1:
        return None, candidates[0][0]

    canonical_ward, ward_district = WARD_TO_DISTRICT.get(
        normalize_place(ward), (ward, None)
    )
    return explicit or ward_district, canonical_ward or None
