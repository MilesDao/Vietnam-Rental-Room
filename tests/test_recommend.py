from src.recsys.recommend import load, recommend


def test_filters_and_order():
    d = load()
    r = recommend(d, 4_000_000, ["Cầu Giấy"], need=["air_conditioner"], top=5)
    assert 0 < len(r) <= 5
    assert (r.price_vnd <= 4_000_000).all() and (r.district == "Cầu Giấy").all()
    assert r.score.is_monotonic_decreasing
    assert recommend(d, 1, top=5).empty


def test_area_imputation_not_used_for_filter():
    d = load()
    assert d.area_est.notna().all() and d.area_imputed.sum() > 0
    r = recommend(d, 6_000_000, min_area=30, top=200)
    assert ((r.area_est >= 30) | r.area_imputed).all()  # unknown areas kept, known ones respected
    assert (d.loc[~d.area_imputed, "area_est"] == d.loc[~d.area_imputed, "area_m2"]).all()


def test_shared_rooms_excluded_by_default():
    d = load()
    assert not recommend(d, 6_000_000, top=100).title.str.contains("ghép|slot", case=False).any()
    assert recommend(d, 6_000_000, top=2000, include_shared=True).title.str.contains("ghép", case=False).any()


def test_fallback_geo_repaired():
    d = load()
    # after regeocode_fallback no shared 35-ward point is left, so the safety net finds nothing
    assert not d.geo_suspect.any()
    assert not ((d.latitude.round(6) == 21.028511) & (d.longitude.round(6) == 105.804817)).any()
    # the fallback point used to put Thạch Thất/Quốc Oai rooms "0.11 km from UTC"
    r = recommend(d, 6_000_000, university="UTC", top=200)
    assert not r.title.str.contains("Thạch Thất|Quốc Oai").any()
    tg = d[d.address.fillna("").str.contains("Xã Trung Giã")].latitude.dropna()
    assert tg.empty or tg.gt(21.2).mean() > 0.9   # empty after a re-crawl that no longer lists Sóc Sơn rooms


def test_price_score_prefers_typical_over_suspiciously_cheap():
    import numpy as np
    from src.recsys.recommend import price_score
    s = price_score(np.array([1e6, 3e6, 4e6]), np.array([3e6] * 3), 4e6)
    assert s[1] == 1 and s[0] < 0.5 and 0.5 <= s[2] < 1
    top = recommend(load(), 4_000_000, university="NEU", top=5)
    assert (top.price_vnd > 1_500_000).sum() >= 3


def test_more_shared_variants_and_dorm_beds():
    import pandas as pd
    from src.recsys.recommend import mark_shared
    t = pd.DataFrame({
        "title": ["Home stay Đại La 1tr", "Địa chỉ: Ngõ 68 Giá: 1tr-1tr250/ng", "Tìm người share phòng",
                  "KTX giường tầng Kim Giang", "Trọ Ký Túc Xá Đại Học Thuỷ Lợi", "ưu tiên hộ gia đình/ng đi làm"],
        "price_vnd": [1e6, 1e6, 1.4e6, 1.2e6, 4.2e6, 4e6],
    })
    assert mark_shared(t).is_shared.tolist() == [True, True, True, True, False, False]


def test_one_room_per_building():
    d = load()
    r = recommend(d, 7_000_000, ["Ba Đình"], top=200)
    from src.clean.sample_schema import _specific_address_key
    full = d.set_index("listing_id").address.map(_specific_address_key)
    keys = (r.district + "|" + r.listing_id.map(full))[r.listing_id.map(full) != ""]
    assert not keys.duplicated().any()
    assert len(recommend(d, 7_000_000, ["Ba Đình"], top=200, per_building=0)) >= len(r)
