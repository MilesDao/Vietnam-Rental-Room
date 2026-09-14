from pathlib import Path

from src.parse.alonhadat_parser import parse_detail_page, parse_list_page

FIXTURES = Path(__file__).parent / "fixtures" / "alonhadat"

DETAIL_URL = "https://alonhadat.com.vn/-chinh-chu-cho-nam-thue-phong-dep-25m-la-khe-ha-dong-19042998.html"


def test_parse_list_page_extracts_cards():
    html = (FIXTURES / "list_page_hanoi.html").read_text(encoding="utf-8")
    rows = parse_list_page(html)
    assert len(rows) >= 10
    first = rows[0]
    assert first["listing_id"].startswith("alonhadat_")
    assert first["url"].startswith("https://alonhadat.com.vn/")
    assert first["title"]
    assert first["area_m2"] is not None


def test_parse_detail_page_fields():
    html = (FIXTURES / "detail_page_1.html").read_text(encoding="utf-8")
    row = parse_detail_page(html, DETAIL_URL)

    assert row["listing_id"] == "alonhadat_19042998"
    assert row["source"] == "alonhadat"
    assert "THU" in row["title"].upper()
    assert row["price_vnd_month"] == 3_000_000
    assert row["price_is_negotiable"] is False
    assert row["area_m2"] == 25.0
    # Legacy (pre-2025-reorg) admin labels, matching mogi's semantics.
    assert row["province"] == "Hà Nội"
    assert row["district"] == "Quận Hà Đông"
    assert row["ward"] == "Phường Hà Đông"
    # Bonus over mogi: the post-reorg admin labels alonhadat's own markup
    # gives for free.
    assert row["admin_new_province"] == "Hà Nội"
    assert row["admin_new_ward"] == "Phường Hà Đông"
    assert row["posted_at"] == "2026-09-11"
    assert row["n_images"] > 0
    # alonhadat pages carry no source-provided coordinates (unlike mogi).
    assert row["lat"] is None and row["lon"] is None
    assert row["geo_confidence"] is None
    # The structured contact field must be hashed, never the raw phone.
    # (The poster's raw phone may still appear inside free-text `description`
    # -- that's the ad copy as authored, not a field we derive or store
    # separately.)
    assert row["phone_hash"] is not None
    assert row["phone_hash"] != "0968688968"
    assert row["phone_prefix"] == "0968"
    assert "0968688968" not in {row["poster_name"], row["phone_hash"], row["poster_id_hash"]}
    assert row["poster_id_hash"] is not None
