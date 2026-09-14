"""Parse mogi.vn list pages and rental-room detail pages into plain dicts.

Pure functions of HTML text (no network calls) so they're unit-testable on
saved fixtures -- see tests/test_mogi_parser.py.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

from src.crawl.pii import hash_value, phone_prefix
from src.parse.vn_text import parse_area_m2, parse_price_vnd

_DETAIL_ID_RE = re.compile(r"-id(\d+)/?(?:[?#].*)?$")
_MAP_LATLON_RE = re.compile(r"[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)")
_PHONE_RE = re.compile(r"PhoneFormat\('(\d{9,11})'\)")
_AGENT_HREF_RE = re.compile(r"/moi-gioi/(\d{9,11})-[^\"']*")


def extract_listing_id(url: str) -> str | None:
    m = _DETAIL_ID_RE.search(url)
    return m.group(1) if m else None


def parse_list_page(html: str, base_url: str = "https://mogi.vn") -> list[dict[str, Any]]:
    """Extract lightweight rows (one per card) from a category list page."""
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict[str, Any]] = []
    for card in soup.select("ul.props > li"):
        link = card.select_one("a.link-overlay")
        if not link or not link.get("href"):
            continue
        url = link["href"]
        if url.startswith("/"):
            url = base_url.rstrip("/") + url
        native_id = extract_listing_id(url)
        if not native_id:
            continue
        attrs = [li.get_text(strip=True) for li in card.select("ul.prop-attr li")]
        area_text = attrs[0] if attrs else None
        rows.append(
            {
                "listing_id": f"mogi_{native_id}",
                "url": url,
                "title": link.get_text(strip=True),
                "address_raw": (card.select_one(".prop-addr") or {}).get_text(strip=True)
                if card.select_one(".prop-addr")
                else None,
                "area_m2": parse_area_m2(area_text),
                "price_raw": (card.select_one(".price").get_text(strip=True))
                if card.select_one(".price")
                else None,
                "n_images": _int_or_none(
                    (card.select_one(".prop-img .total span") or {}).get_text(strip=True)
                    if card.select_one(".prop-img .total span")
                    else None
                ),
            }
        )
    return rows


def _int_or_none(text: str | None) -> int | None:
    if text and text.strip().isdigit():
        return int(text.strip())
    return None


def _breadcrumb_labels(soup: BeautifulSoup) -> list[str]:
    labels = []
    for li in soup.select("ul.breadcrumb li"):
        span = li.select_one("span[property='name']") or li.select_one("span")
        if span:
            labels.append(span.get_text(strip=True))
    return labels


def _parse_posted_at(text: str | None) -> str | None:
    if not text:
        return None
    try:
        return datetime.strptime(text.strip(), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def parse_detail_page(html: str, url: str) -> dict[str, Any]:
    """Parse one mogi.vn phong-tro detail page into the canonical field set."""
    soup = BeautifulSoup(html, "lxml")
    native_id = extract_listing_id(url)

    title_el = soup.select_one(".main-info .title h1")
    address_el = soup.select_one(".main-info .address")
    price_el = soup.select_one(".main-info > .price")
    desc_el = soup.select_one(".info-content-body")

    info: dict[str, str] = {}
    for row in soup.select(".info-attrs .info-attr"):
        spans = row.select("span")
        if len(spans) >= 2:
            info[spans[0].get_text(strip=True)] = spans[1].get_text(strip=True)

    breadcrumb = _breadcrumb_labels(soup)
    # breadcrumb: [Mogi, Cho thuê nhà đất, <province>, <district>, <active title>]
    province = breadcrumb[2] if len(breadcrumb) >= 3 else None
    district = breadcrumb[3] if len(breadcrumb) >= 5 else None

    lat = lon = None
    map_iframe = soup.select_one(".map-content iframe[data-src]")
    if map_iframe:
        m = _MAP_LATLON_RE.search(map_iframe.get("data-src", ""))
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))

    image_urls = [
        img["data-src"]
        for img in soup.select(".media-item img[data-src]")
        if img.get("data-src")
    ]

    agent_name_el = soup.select_one(".agent-info .agent-name a")
    agent_href = agent_name_el.get("href") if agent_name_el else None
    phone_match = _PHONE_RE.search(html) or (
        _AGENT_HREF_RE.search(agent_href) if agent_href else None
    )
    phone = phone_match.group(1) if phone_match else None

    price_text = price_el.get_text(strip=True) if price_el else None
    price_vnd_month, is_negotiable = parse_price_vnd(price_text)

    description = desc_el.decode_contents() if desc_el else None
    if description:
        description = re.sub(r"<br\s*/?>", "\n", description)
        description = BeautifulSoup(description, "lxml").get_text().strip()

    return {
        "listing_id": f"mogi_{native_id}" if native_id else None,
        "source": "mogi",
        "url": url,
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "title": title_el.get_text(strip=True) if title_el else None,
        "description": description,
        "room_type": "phong_tro",
        "price_vnd_month": price_vnd_month,
        "price_raw": price_text,
        "price_is_negotiable": is_negotiable,
        "area_m2": parse_area_m2(info.get("Diện tích sử dụng")),
        "address_raw": address_el.get_text(strip=True) if address_el else None,
        "province": province,
        "district": district,
        "lat": lat,
        "lon": lon,
        "geo_confidence": "geocoded_by_source" if lat is not None else None,
        "legal_status": info.get("Pháp lý"),
        "posted_at": _parse_posted_at(info.get("Ngày đăng")),
        "n_images": len(image_urls),
        "image_urls": image_urls,
        "poster_name": agent_name_el.get_text(strip=True) if agent_name_el else None,
        "poster_id_hash": hash_value(agent_href),
        "phone_hash": hash_value(phone),
        "phone_prefix": phone_prefix(phone),
    }
