"""Unit tests for src/clean -- pure functions, no network, no fixtures needed."""
from __future__ import annotations

import pandas as pd

from src.clean.amenities import extract_amenities
from src.clean.dedup import find_duplicate_clusters, jaccard, shingles
from src.clean.outliers import flag_outliers
from src.clean.text_clean import ascii_fold, normalize_text


def test_normalize_text_collapses_whitespace_and_blank_lines():
    raw = "Cho thuê   phòng\t\tđẹp\n\n\n\ngần  trường"
    out = normalize_text(raw)
    assert out == "Cho thuê phòng đẹp\n\ngần trường"


def test_normalize_text_strips_emoji_and_control_chars():
    raw = "phòng đẹp \U0001F3E0✨ giá rẻ\x0b"
    out = normalize_text(raw)
    assert "\U0001F3E0" not in out
    assert "✨" not in out
    assert "\x0b" not in out
    assert "phòng đẹp" in out


def test_normalize_text_none_passthrough():
    assert normalize_text(None) is None


def test_ascii_fold_strips_diacritics_including_d_stroke():
    assert ascii_fold("Đẹp, không chung chủ, khép kín") == "dep, khong chung chu, khep kin"


def test_ascii_fold_none_passthrough():
    assert ascii_fold(None) is None


def test_extract_amenities_detects_keyword():
    flags = extract_amenities(ascii_fold("Phòng khép kín, có ban công"))
    assert flags["khep_kin"] is True
    assert flags["ban_cong"] is True
    assert flags["thang_may"] is False


def test_extract_amenities_negation_wins_over_positive_substring():
    # "khong chung chu" contains "chung chu" as a substring -- the negative
    # flag must win, not both come back True.
    flags = extract_amenities(ascii_fold("Phòng đẹp, không chung chủ"))
    assert flags["khong_chung_chu"] is True
    assert flags["chung_chu"] is False


def test_extract_amenities_positive_without_negation():
    flags = extract_amenities(ascii_fold("Ở chung chủ, giờ giấc tự do"))
    assert flags["chung_chu"] is True
    assert flags["khong_chung_chu"] is False


_BASE_TITLE = (
    "Cho thuê phòng trọ giá rẻ gần Cầu Giấy đầy đủ nội thất có điều hòa "
    "tủ lạnh máy giặt an ninh tốt"
)


def test_shingles_and_jaccard_near_duplicate_titles():
    a = shingles(_BASE_TITLE)
    b = shingles(_BASE_TITLE + " đẹp")
    c = shingles("Bán căn hộ chung cư cao cấp quận 7 view sông")
    assert jaccard(a, b) >= 0.85
    assert jaccard(a, c) < 0.85


def test_flag_outliers_catches_extreme_price_and_area():
    df = pd.DataFrame({
        "price_vnd_month": [3_000_000, 50_000, 3_200_000],
        "area_m2": [25.0, 20.0, 20000.0],
        "district": ["Quận Cầu Giấy"] * 3,
        "province": ["Hà Nội"] * 3,
    })
    out = flag_outliers(df)
    assert not out.loc[0, "is_outlier"]
    assert out.loc[1, "is_outlier"] and "price_too_low" in out.loc[1, "outlier_reason"]
    assert out.loc[2, "is_outlier"] and "area_too_large" in out.loc[2, "outlier_reason"]


def test_find_duplicate_clusters_merges_near_identical_listings():
    df = pd.DataFrame({
        "listing_id": ["mogi_1", "mogi_2", "mogi_3"],
        "title": [
            _BASE_TITLE,
            _BASE_TITLE + " đẹp",
            "Bán căn hộ chung cư cao cấp quận 7 view sông",
        ],
        "description": ["", "", ""],
        "province": ["Hà Nội", "Hà Nội", "Hà Nội"],
        "area_m2": [25.0, 25.0, 60.0],
        "price_vnd_month": [3_000_000, 3_000_000, 8_000_000],
        "address_norm": ["", "", ""],
    })
    cluster_map, stats = find_duplicate_clusters(df)
    assert cluster_map["mogi_1"] == cluster_map["mogi_2"]
    assert cluster_map["mogi_3"] != cluster_map["mogi_1"]
    assert stats["text_match_pairs"] >= 1


def test_attribute_match_requires_same_address_text_not_just_price_and_area():
    # Regression test: a broker posting many different rooms at the same
    # standardized price/area (common on mogi.vn) must NOT be treated as
    # duplicates just because price and area coincide -- only a shared
    # normalized address counts as the location signal (see dedup.py's
    # module docstring for why coordinate proximity was dropped).
    df = pd.DataFrame({
        "listing_id": ["mogi_1", "mogi_2"],
        "title": ["Phòng Sleep Box đường Bình Thới Quận 11", "Phòng Sleep Box đường Âu Cơ Tân Phú"],
        "description": ["", ""],
        "province": ["TPHCM", "TPHCM"],
        "area_m2": [25.0, 25.0],
        "price_vnd_month": [1_600_000, 1_600_000],
        "address_norm": ["100 binh thoi, quan 11", "au co, tan phu"],
    })
    cluster_map, stats = find_duplicate_clusters(df)
    assert cluster_map["mogi_1"] != cluster_map["mogi_2"]
    assert stats["attribute_match_pairs"] == 0


def test_find_duplicate_clusters_does_not_chain_unrelated_listings_through_a_shared_neighbor():
    # Regression test for the transitive-chaining bug found on real data: a
    # long boilerplate description with one word edited between A->B and a
    # different word edited between B->C can put jaccard(A,B) and
    # jaccard(B,C) both over threshold while jaccard(A,C) stays under it.
    # Single-linkage (naive union-find) would merge all three into one
    # cluster; complete-linkage must keep A/B together and C on its own.
    base_words = (
        "phong tro gia re gan truong dai hoc day du noi that dep thoang mat an ninh tot gio giac tu do sach se "
        "moi xay dien nuoc gia re gan cho gan sieu thi gan benh vien xe bus thuan tien gan cong vien "
        "khu vuc yen tinh an ninh 24 24 co bao ve camera giam sat gan truong hoc mam non tieu hoc "
        "thuan tien di lai gia thue hop ly lien he ngay de xem phong truc tiep"
    ).split()
    a_words = base_words.copy()
    b_words = base_words.copy()
    b_words[6] = "XXX"
    c_words = b_words.copy()
    c_words[60] = "YYY"

    df = pd.DataFrame({
        "listing_id": ["A", "B", "C"],
        "title": ["", "", ""],
        "description": [" ".join(a_words), " ".join(b_words), " ".join(c_words)],
        "province": ["Hà Nội", "Hà Nội", "Hà Nội"],
        "area_m2": [999.0, 999.0, 999.0],  # far apart, so attribute-match can't also fire
        "price_vnd_month": [1_000_000, 2_000_000, 3_000_000],
        "address_norm": ["", "", ""],
    })
    cluster_map, stats = find_duplicate_clusters(df)
    assert cluster_map["A"] == cluster_map["B"]
    assert cluster_map["C"] != cluster_map["A"]
    assert stats["attribute_match_pairs"] == 0
