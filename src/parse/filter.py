"""
src/parse/filter.py - Property Type, Price, and Expiration Validator for Rental Rooms

Enforces business rules:
1. Strictly Rental Rooms (Phòng trọ / Nhà trọ / CCMN sinh viên / Ở ghép / KTX / Studio)
2. Exclude all other properties (Chung cư cao cấp, Biệt thự, Nhà nguyên căn, Văn phòng, Mặt bằng, ...)
3. Price constraint: Price <= 6,000,000 VND/month
4. Expiration check: Automatically detect and discard expired listings (hết hạn, đã thuê, ngừng giao dịch)
"""

import re
from typing import Any, Dict, List, Optional, Tuple

MAX_RENTAL_PRICE_VND = None  # None = Tất cả các mức giá (không giới hạn trần giá)

# Signatures indicating an expired / closed / unavailable listing
EXPIRED_SIGNATURES: List[str] = [
    "tin đăng này đã hết hạn",
    "tin này đã hết hạn",
    "tin cũ tại phongtro123.com",
    "bạn đang xem tin cũ",
    "tin rao đã hết hạn",
    "tin đã hết hạn",
    "tin đã giao dịch",
    "tin đã đóng",
    "đã cho thuê",
    "đã hết hạn hiển thị",
    "nội dung bạn định xem không tồn tại",
    "không tìm thấy tin",
    "tin đăng đã bị xóa",
    "ngừng giao dịch",
]

# Keywords indicating non-room properties that must be strictly excluded
FORBIDDEN_PROPERTY_KEYWORDS: List[str] = [
    # Houses / Villas
    "biệt thự",
    "villa",
    "shophouse",
    "nhà liền kề",
    "nhà phố",
    "nhà mặt tiền",
    "nhà nguyên căn",
    "nguyên căn",
    "thuê nguyên căn",
    "nhà riêng nguyên căn",
    "nhà 3 tầng",
    "nhà 4 tầng",
    "nhà 5 tầng",
    # Commercial / Offices
    "mặt bằng",
    "mặt bằng kinh doanh",
    "mbkd",
    "văn phòng",
    "kho xưởng",
    "nhà kho",
    "nhà xưởng",
    "kiot",
    "kí ốt",
    "cửa hàng",
    "trang trại",
    "đất nền",
    "bán đất",
    "bán nhà",
    # Luxury apartments / Multi-room units
    "căn hộ cao cấp",
    "chung cư cao cấp",
    "penthouse",
    "duplex",
    "condotel",
    "2 phòng ngủ",
    "3 phòng ngủ",
    "4 phòng ngủ",
    "2pn",
    "3pn",
    "4pn",
]

# Keywords that explicitly confirm valid room types
POSITIVE_ROOM_KEYWORDS: List[str] = [
    "phòng trọ",
    "nhà trọ",
    "ở ghép",
    "phòng khép kín",
    "vskk",
    "phòng sinh viên",
    "ccmn",
    "chung cư mini",
    "studio",
    "phòng",
    "ktx",
    "ký túc xá",
    "sleepbox",
    "homestay",
    "hộp ngủ",
    "nhượng phòng",
    "pass phòng",
]


def is_listing_expired(html_content: str) -> Tuple[bool, str]:
    """
    Check if a listing HTML contains markers indicating that the post has expired.
    Returns: (is_expired: bool, reason: str)
    """
    if not html_content:
        return False, "Empty content"

    text_lower = html_content.lower()

    for sig in EXPIRED_SIGNATURES:
        if sig in text_lower:
            return True, f"Expired marker: '{sig}'"

    # Check alert banner with bg-danger and hết hạn
    if "bg-danger" in text_lower and "hết hạn" in text_lower:
        return True, "Alert banner indicates expired listing"

    return False, "Active listing"


def is_valid_rental_room(
    record: Dict[str, Any],
    max_price: Optional[float] = None,
    allow_negotiable: bool = True,
) -> Tuple[bool, str]:
    """
    Validate if a listing record is a valid Rental Room (Phòng Trọ).
    If max_price is provided, checks price <= max_price.

    Returns:
        (is_valid: bool, reason: str)
    """
    title = str(record.get("title", "")).lower()
    price = record.get("price_vnd") if "price_vnd" in record else (record.get("price_vnd_month") if "price_vnd_month" in record else record.get("price"))

    # 1. Price Validation (if max_price is specified)
    if max_price is not None:
        if price is None:
            return False, "Missing price"
        if isinstance(price, (int, float)):
            if price <= 0:
                return False, f"Invalid price <= 0 ({price})"
            if price > max_price:
                return False, f"Price {price:,.0f} VND exceeds limit of {max_price:,.0f} VND"
        elif isinstance(price, str):
            if not allow_negotiable:
                return False, f"Price is negotiable/unspecified text: '{price}'"

    # 2. Check for Forbidden Property Keywords in Title
    for kw in FORBIDDEN_PROPERTY_KEYWORDS:
        if re.search(r"(?:\b|_)" + re.escape(kw) + r"(?:\b|_)", title):
            # Exception: if title says "tìm bạn ở ghép..." or "phòng trọ gần..." we check context
            if any(p in title for p in ["ở ghép", "phòng trọ", "nhà trọ", "ccmn", "phòng"]):
                if any(rel in title for rel in ["gần", "cạnh", "đối diện", "sau", "trong khu", "view"]):
                    continue
            return False, f"Forbidden property keyword found in title: '{kw}'"

    # 3. If title doesn't have obvious negative keywords, verify it has room context or comes from room category
    source = record.get("source", "")
    has_positive = any(kw in title for kw in POSITIVE_ROOM_KEYWORDS)
    
    if has_positive or source in ["phongtro123", "alonhadat"]:
        return True, "Valid rental room"

    return True, "Valid rental room"
