"""Parse alonhadat.com.vn list pages and rental-room detail pages into plain dicts.

Pure functions of HTML text (no network calls) so they're unit-testable on
saved fixtures -- see tests/test_alonhadat_parser.py. Mirrors
src/parse/mogi_parser.py's shape and canonical field set; see
docs/alonhadat_scraping.md for how the two sites' markup differs.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

from src.crawl.pii import hash_value, phone_prefix
from src.parse.vn_text import parse_area_m2, parse_price_vnd

_DETAIL_ID_RE = re.compile(r"-(\d+)\.html$")
_MEMBER_ID_RE = re.compile(r"id=['\"]hddNguoiDang['\"]\s+value=['\"](\d+)['\"]")
_OLD_ADDRESS_SUFFIX_RE = re.compile(r"\(c[ũu]\)|\(địa chỉ c[ũu]\)", re.IGNORECASE)
_PLACEHOLDER_VALUES = {"", "-", "--", "---", "_"}


def extract_listing_id(url: str) -> str | None:
    m = _DETAIL_ID_RE.search(url)
    return m.group(1) if m else None


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    text = text.strip()
    return text or None


def _placeholder_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    return None if value.strip() in _PLACEHOLDER_VALUES else value.strip()


def _parse_old_address(text: str | None) -> dict[str, str | None]:
    """Split alonhadat's legacy ", ward, district, province" text.

    alonhadat re-displays every listing's address twice: a *current* address
    against the 2025 admin reorg's new province/ward (schema.org itemprops),
    and this *old* one against the pre-reorg province/district/ward -- see
    docs/PLAN.md's "Vietnam reorganized its provincial/commune structure in
    2025" note. The old-address text is exactly the legacy label PLAN.md's
    Phase 3 crosswalk wants alongside the new admin code, so both are kept
    (mogi only ever gives you the legacy one).

    The trailing "(cũ)" / "(địa chỉ cũ)" marker rendered next to this text
    sometimes lands inside the tag we scrape and sometimes just outside it
    (a markup quirk of the site, not ours) -- stripped defensively either way.
    Empty segments (a listing with no street, or "streetAddress,," rendering)
    are dropped rather than kept as blanks.
    """
    if not text:
        return {"ward": None, "district": None, "province": None, "street": None}
    text = _OLD_ADDRESS_SUFFIX_RE.sub("", text).strip()
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if not parts:
        return {"ward": None, "district": None, "province": None, "street": None}
    province = parts[-1]
    district = parts[-2] if len(parts) >= 2 else None
    ward = parts[-3] if len(parts) >= 3 else None
    street = ", ".join(parts[:-3]) if len(parts) > 3 else None
    return {"ward": ward, "district": district, "province": province, "street": street}


def parse_list_page(html: str, base_url: str = "https://alonhadat.com.vn") -> list[dict[str, Any]]:
    """Extract lightweight rows (one per card) from a category list page."""
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict[str, Any]] = []
    for card in soup.select("article.property-item"):
        link = card.select_one("a[itemprop='url']")
        if not link or not link.get("href"):
            continue
        url = link["href"]
        if url.startswith("/"):
            url = base_url.rstrip("/") + url
        native_id = extract_listing_id(url)
        if not native_id:
            continue
        title_el = card.select_one("[itemprop='name']")
        price_el = card.select_one("[itemprop='price']")
        area_el = card.select_one("[itemprop='floorSize'] [itemprop='value']")
        rows.append(
            {
                "listing_id": f"alonhadat_{native_id}",
                "url": url,
                "title": title_el.get_text(strip=True) if title_el else None,
                "address_raw": _clean(
                    (card.select_one("p.old-address") or {}).get_text(strip=True)
                    if card.select_one("p.old-address")
                    else None
                ),
                "area_m2": float(area_el.get_text(strip=True)) if area_el else None,
                "price_raw": price_el.get_text(strip=True) if price_el else None,
            }
        )
    return rows


def _parse_more_info_table(root: BeautifulSoup) -> dict[str, str | None]:
    """The 3-pairs-per-row "Các thông tin khác" table -- key/value <td> cells."""
    info: dict[str, str | None] = {}
    for row in root.select("section.moreinfor1 table tr"):
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        for i in range(0, len(cells) - 1, 2):
            info[cells[i]] = _placeholder_to_none(cells[i + 1])
    return info


def parse_detail_page(html: str, url: str) -> dict[str, Any]:
    """Parse one alonhadat.com.vn phong-tro detail page into the canonical field set."""
    soup = BeautifulSoup(html, "lxml")
    native_id = extract_listing_id(url)
    root = soup.select_one("article.property") or soup

    title_el = root.select_one("[itemprop='name']")
    desc_el = root.select_one("[itemprop='description']")
    price_el = root.select_one("section.more-info [itemprop='price']")
    area_el = root.select_one("[itemprop='floorSize'] [itemprop='value']")
    time_el = root.select_one("[itemprop='datePosted']")

    price_text = price_el.get_text(strip=True) if price_el else None
    price_attr = (price_el.get("value") or price_el.get("content")) if price_el else None
    if price_attr:
        price_vnd_month, is_negotiable = float(price_attr), False
    else:
        # Fallback for whatever this run's markup doesn't structure as
        # microdata (e.g. a future "Thỏa thuận" listing with no price attr).
        price_vnd_month, is_negotiable = parse_price_vnd(price_text)

    area_text = area_el.get_text(strip=True) if area_el else None
    area_m2 = float(area_text) if area_text else parse_area_m2(area_text)

    new_address_el = root.select_one("[itemprop='address']")
    new_ward = _clean(
        new_address_el.select_one("[itemprop='addressLocality']").get_text(strip=True)
        if new_address_el and new_address_el.select_one("[itemprop='addressLocality']")
        else None
    )
    new_province = _clean(
        new_address_el.select_one("[itemprop='addressRegion']").get_text(strip=True)
        if new_address_el and new_address_el.select_one("[itemprop='addressRegion']")
        else None
    )

    old_address_el = root.select_one("p.old-address")
    old_address_text = old_address_el.get_text(strip=True) if old_address_el else None
    old = _parse_old_address(old_address_text)

    image_urls = []
    for img in root.select("section.images ul.image-list img"):
        src = img.get("src")
        if not src:
            continue
        image_urls.append(src if src.startswith("http") else "https://alonhadat.com.vn" + src)

    contact_root = soup.select_one("aside.right section.contact")
    poster_name_el = contact_root.select_one(".name") if contact_root else None
    phone_link = contact_root.select_one(".fone a") if contact_root else None
    phone_digits = None
    if phone_link:
        href = phone_link.get("href", "")
        raw_phone = href.removeprefix("tel:") or phone_link.get_text(strip=True)
        phone_digits = re.sub(r"\D", "", raw_phone) or None

    member_id_match = _MEMBER_ID_RE.search(html)
    member_id = member_id_match.group(1) if member_id_match else None

    info = _parse_more_info_table(root)

    description = desc_el.get_text(separator="\n", strip=True) if desc_el else None

    return {
        "listing_id": f"alonhadat_{native_id}" if native_id else None,
        "source": "alonhadat",
        "url": url,
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "title": title_el.get_text(strip=True) if title_el else None,
        "description": description,
        "room_type": "phong_tro",
        "price_vnd_month": price_vnd_month,
        "price_raw": price_text,
        "price_is_negotiable": is_negotiable,
        "area_m2": area_m2,
        # address_raw/province/district use the legacy (old-address) labels,
        # matching mogi's semantics -- see _parse_old_address's docstring.
        "address_raw": _clean(old_address_text and _OLD_ADDRESS_SUFFIX_RE.sub("", old_address_text).strip()),
        "province": old["province"],
        "district": old["district"],
        "ward": old["ward"],
        # Bonus over mogi: alonhadat's markup also gives the CURRENT
        # (post-2025-reorg) admin labels for free, straight from the page's
        # own schema.org markup -- exactly the crosswalk pairing docs/PLAN.md
        # Phase 3 asks for. mogi never surfaces new-scheme labels at all.
        "admin_new_province": new_province,
        "admin_new_ward": new_ward,
        "lat": None,
        "lon": None,
        # Never observed with source-provided coordinates during recon
        # (docs/alonhadat_scraping.md) -- unlike mogi's embedded map iframe.
        "geo_confidence": None,
        "legal_status": info.get("Pháp lý"),
        "posted_at": time_el.get("datetime") if time_el else None,
        "n_images": len(image_urls),
        "image_urls": image_urls,
        "poster_name": poster_name_el.get_text(strip=True) if poster_name_el else None,
        "poster_id_hash": hash_value(member_id),
        "phone_hash": hash_value(phone_digits),
        "phone_prefix": phone_prefix(phone_digits),
    }
