from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from src.clean.sample_schema import (
    AMENITY_COLUMNS,
    HANOI_DISTRICTS,
    SAMPLE_COLUMNS,
    clean_sample_frame,
    clean_ward,
    coordinate_issues,
    hash_contact,
    mark_duplicates,
    normalize_district,
)
from src.clean.text_clean import ascii_fold
from src.crawl.pii import hash_value

FIXTURES = Path(__file__).parent / "fixtures" / "alonhadat"


def make_row(**overrides):
    row = {c: None for c in SAMPLE_COLUMNS}
    row.update(
        platform="Mogi.vn", listing_id="mogi_1", title="Phòng trọ đẹp",
        district="Quận Hà Đông", ward="Cho thuê Nhà trọ Trần Phú",
        address="Trần Phú, Phường Mộ Lao, Quận Hà Đông, Hà Nội",
        price_vnd=3_000_000, house_type="phong_tro", area_m2=25,
        latitude=20.98, longitude=105.78,
        contact_phone="0917831531", contact_zalo="0917831531",
        image_count=3, listing_url="https://example.test/1",
    )
    for col in AMENITY_COLUMNS:
        row[col] = False
    row.update(overrides)
    return row


def test_district_table_matches_alonhadat_select():
    soup = BeautifulSoup((FIXTURES / "detail_page_1.html").read_text(encoding="utf-8"), "lxml")
    labels = {
        o.get_text(strip=True)
        for o in soup.select("select.district option")
        if o.get("value") != "0"
    }
    assert {ascii_fold(d) for d in HANOI_DISTRICTS} == {ascii_fold(label) for label in labels}


def test_normalize_district_variants():
    assert normalize_district("Đống Đa") == "Quận Đống Đa"
    assert normalize_district("Quận Hoàng Mai") == "Quận Hoàng Mai"
    assert normalize_district("huyen thanh tri") == "Huyện Thanh Trì"
    assert normalize_district("Hai Ba Trung") == "Quận Hai Bà Trưng"
    assert normalize_district("Ứng Hoà") == "Huyện Ứng Hòa"
    assert normalize_district("Chưa rõ") is None
    assert normalize_district(None) is None


def test_clean_ward_rules():
    # mogi: breadcrumb junk in the ward column, the real ward is in the address
    assert clean_ward("Cho thuê Nhà trọ Trần Phú",
                      "Trần Phú, Phường Mộ Lao, Quận Hà Đông, Hà Nội",
                      "Quận Hà Đông") == "Phường Mộ Lao"
    # Rencity: bare name in a quận gets the phường prefix
    assert clean_ward("Dịch Vọng", "Số 4 Ngõ 322 Mỹ Đình 1", "Quận Cầu Giấy") == "Phường Dịch Vọng"
    # 2025-scheme wards often reuse an old district's name: kept as a ward
    assert clean_ward("Thanh Xuân", "Số 2 ngõ 90 Miếu Đầm", "Quận Thanh Xuân") == "Phường Thanh Xuân"
    # a huyện's unit could be a xã or a thị trấn: left bare
    assert clean_ward("Tân Triều", "Yên Xá", "Huyện Thanh Trì") == "Tân Triều"
    assert clean_ward(None, "162 Đức Giang", None) is None


def test_coordinate_issues_rejects_placeholders():
    lat = pd.Series([21.03, 10.77203, 14.058324, 85.05112877980659, None])
    lon = pd.Series([105.80, 106.69832, 108.277199, -180, 105.8])
    assert coordinate_issues(lat, lon).tolist() == [
        None, "outside_hanoi", "outside_hanoi", "outside_hanoi", "missing",
    ]


def test_hash_contact_normalizes_before_hashing():
    expected = hash_value("0917831531")
    assert hash_contact("0917831531") == expected
    assert hash_contact("0917.831.531") == expected
    assert hash_contact("+84 917 831 531") == expected
    assert hash_contact(917831531) == expected          # leading zero lost upstream
    assert hash_contact(expected) == expected           # already hashed (alonhadat export)
    assert hash_contact("12345") is None
    assert hash_contact(float("nan")) is None


def test_clean_sample_frame_core_rules():
    df = pd.DataFrame([
        make_row(),
        make_row(listing_id="PT_1", platform="PhongTot.com", district="Đống Đa", ward=None,
                 address="Đường Láng, Quận Đống Đa, Hà Nội", price_vnd=0,
                 house_type="Phòng trọ", latitude=None, longitude=None,
                 contact_phone="+84 917 831 531", contact_zalo=None),
        make_row(listing_id="RC_1", platform="Rencity.vn", district="Chưa rõ", ward="Dịch Vọng",
                 address="162 Đức Giang", price_vnd=800_000_000, area_m2=None,
                 latitude=85.05112877980659, longitude=-180,
                 contact_phone=None, contact_zalo=None),
    ])
    out = clean_sample_frame(df)
    mogi, phongtot, rencity = out.iloc[0], out.iloc[1], out.iloc[2]

    assert mogi["ward"] == "Phường Mộ Lao"
    assert mogi["house_type"] == "Phòng trọ"
    assert mogi["coord_issue"] is None and mogi["geo_source"] == "listing"

    assert phongtot["district"] == "Quận Đống Đa"
    assert pd.isna(phongtot["price_vnd"]) and phongtot["price_missing"]
    assert phongtot["coord_issue"] == "missing"
    assert phongtot["contact_phone"] == mogi["contact_phone"] == hash_value("0917831531")

    assert pd.isna(rencity["district"])
    assert rencity["coord_issue"] == "outside_hanoi" and pd.isna(rencity["latitude"])
    assert rencity["latitude_orig"] == 85.05112877980659
    assert rencity["is_outlier"] and "price_too_high" in rencity["outlier_reason"]

    assert "0917831531" not in out.to_csv()
    assert len(out) == 3


def test_mark_duplicates_same_platform_only():
    base = dict(title="Cho thuê phòng trọ giá rẻ", district="Quận Cầu Giấy",
                address="Ngõ 1 Xuân Thủy", ward=None, price_vnd=3_000_000.0, area_m2=20.0)
    df = pd.DataFrame([
        make_row(listing_id="a", **base),
        make_row(listing_id="b", **{**base, "price_vnd": 3_100_000.0}),   # within 5%: same room
        make_row(listing_id="c", **{**base, "price_vnd": 4_000_000.0}),   # different room
        make_row(listing_id="d", platform="PhongTot.com", **base),         # other platform
    ])
    out = mark_duplicates(clean_sample_frame(df))
    dup_of = dict(zip(out["listing_id"], out["duplicate_of"]))
    assert dup_of["b"] == "a"
    assert pd.isna(dup_of["a"]) and pd.isna(dup_of["c"]) and pd.isna(dup_of["d"])
    assert out.set_index("listing_id").loc["a", "n_duplicates"] == 1


def test_mark_duplicates_does_not_chain():
    base = dict(title="Cho thuê phòng trọ giá rẻ", district="Quận Cầu Giấy",
                address="Ngõ 1 Xuân Thủy", ward=None, area_m2=20.0)
    # a~b and b~c are each within 5%, but a and c are ~9% apart
    df = pd.DataFrame([
        make_row(listing_id="a", price_vnd=3_000_000.0, **base),
        make_row(listing_id="b", price_vnd=3_140_000.0, **base),
        make_row(listing_id="c", price_vnd=3_290_000.0, **base),
    ])
    out = mark_duplicates(clean_sample_frame(df))
    dup_of = dict(zip(out["listing_id"], out["duplicate_of"]))
    assert dup_of["b"] == "a"
    assert pd.isna(dup_of["c"])


def test_mark_duplicates_ignores_addresses_without_a_number():
    # PhongTot: street-level address, no price. mogi: neighbourhood-level
    # address, same price and area. Different titles -> different rooms.
    rows = [
        make_row(listing_id="p1", platform="PhongTot.com", title="Phòng studio ban công",
                 district="Quận Ba Đình", ward=None, address="Phố Kim Mã, Quận Ba Đình, Hà Nội",
                 price_vnd=0, area_m2=25.0),
        make_row(listing_id="p2", platform="PhongTot.com", title="Căn hộ mini gần hồ",
                 district="Quận Ba Đình", ward=None, address="Phố Kim Mã, Quận Ba Đình, Hà Nội",
                 price_vnd=0, area_m2=25.0),
        make_row(listing_id="m1", title="CCMN Ngõ 87 Yên Xá gác xép", district="Huyện Thanh Trì",
                 address="Yên Xá, Xã Tân Triều, Huyện Thanh Trì, Hà Nội", price_vnd=3_800_000, area_m2=25),
        make_row(listing_id="m2", title="Phòng trọ mới xây tại 39 Yên Xá", district="Huyện Thanh Trì",
                 address="Yên Xá, Xã Tân Triều, Huyện Thanh Trì, Hà Nội", price_vnd=3_800_000, area_m2=25),
    ]
    out = mark_duplicates(clean_sample_frame(pd.DataFrame(rows)))
    assert out["duplicate_of"].isna().all()


def test_mark_duplicates_matches_house_level_address():
    base = dict(platform="Rencity.vn", district="Quận Đống Đa", ward="Kim Liên",
                address="36 Ngõ 100 Yên Lãng", price_vnd=4_500_000, area_m2=None)
    df = pd.DataFrame([
        make_row(listing_id="RC_1", title="Căn hộ 1K1N full nội thất", **base),
        make_row(listing_id="RC_2", title="Studio mới tinh gần Thái Hà", **base),
    ])
    out = mark_duplicates(clean_sample_frame(df))
    assert dict(zip(out["listing_id"], out["duplicate_of"]))["RC_2"] == "RC_1"


def test_area_ranges_become_midpoint_with_bounds():
    df = pd.DataFrame([
        make_row(area_m2="20 - 27"),
        make_row(listing_id="x", area_m2="25 - 25"),
        make_row(listing_id="y", area_m2="abc"),
    ])
    out = clean_sample_frame(df)
    assert out.loc[0, "area_m2"] == 23.5 and out.loc[0, "area_is_range"]
    assert (out.loc[0, "area_m2_min"], out.loc[0, "area_m2_max"]) == (20, 27)
    assert out.loc[1, "area_m2"] == 25 and not out.loc[1, "area_is_range"]
    assert pd.isna(out.loc[2, "area_m2"]) and out.loc[2, "area_missing"]
