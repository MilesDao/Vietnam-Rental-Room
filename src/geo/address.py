"""Turn a listing's free-text Hanoi address into Nominatim search candidates.

Pure functions, no network (requests live in src/geo/nominatim.py), so query
building and result checking are unit-testable.

Probing the public Nominatim instance on 2026-09-12 shaped two rules here:

- OpenStreetMap has no district level in Hanoi since the 2025 reform. Old
  districts and wards survive as `boundary=historic` areas, and putting
  "Quận Cầu Giấy" into a street query makes it fail or match something else.
  So districts only bound the search box (nominatim.py), never the query text.
- Nominatim returns its best fuzzy guess even when it's wrong: "Ngõ 73 Phùng
  Khoang" came back as Ngõ 30, "Đường Ngọc Hà" as a company, "Phường Thanh
  Xuân Bắc" as a college 7 km away. Every result is checked against what was
  asked -- the right kind of place with the right name -- before it's used.

House numbers are stripped and never sent: they rarely geocode in Hanoi's
alleys, and the usage policy asks for no personal data in queries.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.clean.text_clean import ascii_fold

CITY = "Hà Nội"
COUNTRY = "Việt Nam"


@dataclass(frozen=True)
class StreetParts:
    street: str | None   # as written, e.g. "Trường Chinh"
    prefix: str | None   # "Đường" / "Phố" when the address had one
    alley: str | None    # "580" for "Ngõ 580 Trường Chinh"


@dataclass(frozen=True)
class Candidate:
    level: str                   # "alley" | "street" | "ward" | "district" | "city"
    query: str                   # free-form Nominatim `q`
    name: str                    # folded street/ward/district name the result must carry
    alley: str | None = None     # alley number an "alley" result must carry
    district: str | None = None  # district whose box bounds the search; None = the whole city
    city: str = CITY             # province the address is in; bounds the search when not Hà Nội


_PAREN_RE = re.compile(r"\([^)]*\)")
# Admin segments ("Phường X", "Quận Y", "Hà Nội") are dropped from the street part.
# "Xã" isn't treated as admin in the first segment: "Xã Đàn" is a street.
_ADMIN_SEGMENT_RE = re.compile(
    r"^(phường|xã|thị trấn|quận|huyện|thị xã|thành phố|tp\.?|hà nội|việt nam)(\s|$)", re.I
)
_FIRST_ADMIN_SEGMENT_RE = re.compile(
    r"^(phường|thị trấn|quận|huyện|thị xã|thành phố|tp\.?|hà nội|việt nam)(\s|$)", re.I
)
_ALLEY_RE = re.compile(r"\b(?:ngõ|ngo)\s*(\d+[a-z]?)(?:\s*/\s*\d+[a-z]?)*", re.I)
_SUB_ALLEY_RE = re.compile(r"\b(?:ngách|ngach|hẻm|hem|kiệt|kiet)\s*\d+[a-z]?(?:\s*/\s*\d+[a-z]?)*", re.I)
_HOUSE_WORD_RE = re.compile(r"^(?:số nhà|số|sn|nhà|tổ|lô)\s*(?=\d)", re.I)
_SLASH_NUMBER_RE = re.compile(r"^\d+[a-z]?(?:\s*/\s*\d+[a-z]?)+", re.I)
_HOUSE_RE = re.compile(r"^(?:(?:số nhà|số|sn|nhà|tổ|lô)\s*)?\d+[a-z]?\b\s*", re.I)
_STREET_PREFIX_RE = re.compile(r"^(mặt phố|mặt đường|phố|đường)\s+", re.I)
_PREFIX_DISPLAY = {"mặt phố": "Phố", "mặt đường": "Đường", "phố": "Phố", "đường": "Đường"}
_ADMIN_PREFIX_RE = re.compile(r"^(phường|xã|thị trấn|quận|huyện|thị xã)\s+", re.I)

# Applied to ascii-folded result names.
_ROAD_ALLEY_NAME_RE = re.compile(r"^(?:ngo|ngach|hem|kiet)\s+(\d+[a-z]?)(?:\s*/\s*\d+[a-z]?)*\s+")
_AREA_NAME_PREFIX_RE = re.compile(r"^(?:phuong|xa|thi tran|quan|huyen|thi xa)\s+")


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", ascii_fold(text)).strip()


# The 34 provinces of Vietnam's 2025 reorganization (same set as the slugs in
# config/sources.yaml), plus aliases that turn up in listing text. Used only to
# notice an address that isn't in Hanoi at all -- sample.csv carries a few --
# so its search can be bounded by the right city instead of Hanoi's box.
VN_PROVINCES = (
    "Hà Nội", "Hải Phòng", "Huế", "Đà Nẵng", "Khánh Hòa", "Hồ Chí Minh", "Cần Thơ", "An Giang",
    "Bắc Ninh", "Cà Mau", "Cao Bằng", "Đắk Lắk", "Điện Biên", "Đồng Nai", "Đồng Tháp", "Gia Lai",
    "Hà Tĩnh", "Hưng Yên", "Lai Châu", "Lâm Đồng", "Lạng Sơn", "Lào Cai", "Nghệ An", "Ninh Bình",
    "Phú Thọ", "Quảng Ngãi", "Quảng Ninh", "Quảng Trị", "Sơn La", "Tây Ninh", "Thái Nguyên",
    "Thanh Hóa", "Tuyên Quang", "Vĩnh Long",
)
_PROVINCE_ALIASES = {
    "tphcm": "Hồ Chí Minh", "tp hcm": "Hồ Chí Minh", "hcm": "Hồ Chí Minh",
    "sai gon": "Hồ Chí Minh", "ho chi minh city": "Hồ Chí Minh", "ha noi": "Hà Nội",
}
_PROVINCE_BY_FOLD = {fold(p): p for p in VN_PROVINCES} | _PROVINCE_ALIASES
_CITY_PREFIX_RE = re.compile(r"^(tp\.?|thành phố|tỉnh)\s*", re.I)


def detect_city(address: str | None) -> str:
    """The province named in the address; Hà Nội when none is named."""
    if not address:
        return CITY
    for segment in reversed([s.strip() for s in address.split(",") if s.strip()]):
        name = _PROVINCE_BY_FOLD.get(fold(_CITY_PREFIX_RE.sub("", segment)))
        if name:
            return name
    return CITY


def parse_street(address: str | None) -> StreetParts:
    """Split an address into street name, optional Đường/Phố prefix and alley number.

    Alley conventions differ: "ngõ 102/35 X" names alley 102 off street X
    (the first number after the keyword), while a bare "168/553 Giải Phóng"
    names alley 553 (the last number before the street).
    """
    if not address:
        return StreetParts(None, None, None)
    segments = [s.strip() for s in _PAREN_RE.sub(" ", address).split(",")]
    kept = [
        s for i, s in enumerate(segments)
        if s and not (_ADMIN_SEGMENT_RE if i else _FIRST_ADMIN_SEGMENT_RE).match(s)
        and not (i and fold(_CITY_PREFIX_RE.sub("", s)) in _PROVINCE_BY_FOLD)
    ]
    text = re.sub(r"\s+", " ", " ".join(kept)).strip()

    alley = None
    matches = list(_ALLEY_RE.finditer(text))
    if matches:
        alley = matches[-1].group(1)
        rest = text[matches[-1].end():]
    else:
        rest = _HOUSE_WORD_RE.sub("", _SUB_ALLEY_RE.sub(" ", text).strip())
        m = _SLASH_NUMBER_RE.match(rest)
        if m:
            alley = re.split(r"\s*/\s*", m.group(0))[-1]
            rest = rest[m.end():]
    rest = _HOUSE_RE.sub("", _SUB_ALLEY_RE.sub(" ", rest).strip()).strip()

    prefix = None
    while m := _STREET_PREFIX_RE.match(rest):
        prefix = _PREFIX_DISPLAY[m.group(1).lower()]
        rest = rest[m.end():].strip()
    street = rest.strip(" -.") or None
    return StreetParts(street=street, prefix=prefix if street else None, alley=alley if street else None)


def area_candidate(name: str, city: str = CITY) -> Candidate:
    """Query for an administrative area: a district inside its city, or a city itself."""
    name = name.strip()
    is_city = fold(name) == fold(city)
    return Candidate(
        "city" if is_city else "district",
        f"{name}, {COUNTRY if is_city else city}",
        fold(_ADMIN_PREFIX_RE.sub("", name)),
        None, None, city,
    )


def _without_area_suffix(street: str, *areas: str | None) -> str:
    """Drop a district or ward name glued onto the street.

    "Lê Trọng Tấn Thanh Xuân" (PhongTot appends the district) and
    "Lê Văn Chí Linh Xuân" (an address whose ward segment isn't prefixed).
    """
    for area in areas:
        if not area:
            continue
        area_words = _ADMIN_PREFIX_RE.sub("", area.strip()).split()
        words = street.split()
        n = len(area_words)
        if len(words) > n and fold(" ".join(words[-n:])) == fold(" ".join(area_words)):
            street = " ".join(words[:-n])
    return street


def build_candidates(address: str | None, ward: str | None, district: str | None) -> list[Candidate]:
    """Queries to try in order, most precise first: alley, street, ward, district/city."""
    out: list[Candidate] = []
    city = detect_city(address)
    if city != CITY:
        # Not a Hanoi address, so a Hanoi district can't bound it; its own city does.
        district = None
    parts = parse_street(address)
    if parts.street:
        street = _without_area_suffix(parts.street, district, ward)
        shown = f"{parts.prefix} {street}" if parts.prefix else street
        core = fold(street)
        if parts.alley:
            out.append(Candidate("alley", f"Ngõ {parts.alley} {shown}, {city}", core, parts.alley, district, city))
        out.append(Candidate("street", f"{shown}, {city}", core, None, district, city))
        # OSM names most of these roads "Phố X" or "Đường X" whatever the listing
        # wrote, and ", Hà Nội" pulls in POIs named "... Hà Nội" -- while "Đường"
        # alone also matches railways ("Đường sắt"). On 12 streets that had failed
        # (2026-09-12), "Phố X" with no city found every one; the bare name lost
        # to same-named wards. So fall back to the other prefix(es), no city.
        for alt in ("Phố", "Đường"):
            if parts.prefix != alt:
                out.append(Candidate("street", f"{alt} {street}", core, None, district, city))
    if ward and ward.strip():
        ward = ward.strip()
        bare = _ADMIN_PREFIX_RE.sub("", ward).strip()
        out.append(Candidate("ward", f"{ward}, {city}", fold(bare), None, district, city))
        if bare != ward:
            out.append(Candidate("ward", f"{bare}, {city}", fold(bare), None, district, city))
    if district and district.strip():
        out.append(area_candidate(district, city))
    elif city != CITY:
        out.append(area_candidate(city, city))
    return out


def _road_name_matches(rest: str, core: str) -> bool:
    # core itself may start with "duong" (Dương Quảng Hàm), so compare whole names
    return rest in {core, f"duong {core}", f"pho {core}"}


def accept_result(candidate: Candidate, result: dict) -> bool:
    """Whether one Nominatim result is really the place the candidate asked for."""
    name = fold(result.get("name") or "")
    category = result.get("category")
    if candidate.level in ("alley", "street"):
        if category != "highway":
            return False
        m = _ROAD_ALLEY_NAME_RE.match(name)
        if candidate.level == "alley":
            return (
                m is not None
                and m.group(1) == (candidate.alley or "").lower()
                and _road_name_matches(name[m.end():], candidate.name)
            )
        # The street itself, or any alley opening onto it, puts the listing on that street.
        return _road_name_matches(name[m.end():] if m else name, candidate.name)
    if category not in ("boundary", "place"):
        return False
    return _AREA_NAME_PREFIX_RE.sub("", name) == candidate.name


def pick_result(candidate: Candidate, results: list[dict]) -> dict | None:
    return next((r for r in results if accept_result(candidate, r)), None)
