from pathlib import Path

from src.parse.mogi_parser import parse_detail_page, parse_list_page
from src.parse.vn_text import parse_area_m2, parse_price_vnd

FIXTURES = Path(__file__).parent / "fixtures" / "mogi"

DETAIL_URL = (
    "https://mogi.vn/quan-hoan-kiem/thue-phong-tro-khu-nha-tro/"
    "cho-thue-ngan-han-va-dai-han-homestay-29b-hang-khay-13-ba-trieu-id22750786"
)


def test_parse_list_page_extracts_cards():
    html = (FIXTURES / "list_page_hanoi.html").read_text(encoding="utf-8")
    rows = parse_list_page(html)
    assert len(rows) >= 10
    first = rows[0]
    assert first["listing_id"].startswith("mogi_")
    assert first["url"].startswith("https://mogi.vn/")
    assert first["title"]
    assert first["area_m2"] is not None


def test_parse_detail_page_fields():
    html = (FIXTURES / "detail_page_1.html").read_text(encoding="utf-8")
    row = parse_detail_page(html, DETAIL_URL)

    assert row["listing_id"] == "mogi_22750786"
    assert row["source"] == "mogi"
    assert "Homestay" in row["title"]
    assert row["price_vnd_month"] == 2_000_000
    assert row["price_is_negotiable"] is False
    assert row["area_m2"] == 15.0
    assert row["province"] == "Hà Nội"
    assert row["district"] == "Quận Hoàn Kiếm"
    assert row["posted_at"] is not None
    assert row["n_images"] > 0
    assert row["lat"] is not None and row["lon"] is not None
    # The structured contact field must be hashed, never the raw phone.
    # (The poster's raw phone may still appear inside free-text `description`
    # -- that's the ad copy as authored, not a field we derive or store separately.)
    assert row["phone_hash"] is not None
    assert row["phone_hash"] != "0917831531"
    assert "0917831531" not in {row["poster_name"], row["phone_hash"], row["poster_id_hash"]}


def test_parse_price_vnd_variants():
    assert parse_price_vnd("2 triệu")[0] == 2_000_000
    assert parse_price_vnd("2 triệu 700 nghìn")[0] == 2_700_000
    assert parse_price_vnd("5 triệu 500 nghìn")[0] == 5_500_000
    assert parse_price_vnd("Thỏa thuận") == (None, True)


def test_parse_area_m2_variants():
    assert parse_area_m2("15 m2") == 15.0
    assert parse_area_m2("25,5 m²") == 25.5
    assert parse_area_m2(None) is None
