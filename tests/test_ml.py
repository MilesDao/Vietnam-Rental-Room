import numpy as np
import pandas as pd

from src.recsys import feedback, ltr, price_model
from src.recsys.prepare import hash_phone
from src.recsys.recommend import campus_distance, load, price_score, recommend
from src.recsys.similar import Index


def test_campus_distance_uses_the_chosen_campus():
    neu = pd.DataFrame({"latitude": [20.9965], "longitude": [105.8425]})   # NEU's own coordinates
    assert campus_distance(neu, "NEU").iloc[0] < 0.01
    assert campus_distance(neu, "UTC").iloc[0] > 4
    d = load()
    r = recommend(d, 6_000_000, university="NEU", max_uni_km=1.5, top=50)
    assert (r.distance_to_target_km <= 1.5).all()


def test_budget_anchor_lifts_high_budgets():
    typical, cheap, mid = np.array([3e6, 3e6]), 3e6, 9e6
    s = price_score(np.array([cheap, mid]), typical, 12e6)
    assert s[1] > s[0]   # with 12 M to spend, a 9 M room fits better than a 3 M one


def test_hash_phone_never_returns_a_raw_number():
    raw = hash_phone("0912 345 678")
    assert raw != "0912345678" and len(raw) == 16
    assert hash_phone("a3f09b12c4d5e6f7") == "a3f09b12c4d5e6f7"   # already hashed stays put
    assert hash_phone("0" * 15 + "1") == "0" * 15 + "1"          # a digit-only hash is not re-hashed
    assert hash_phone(912345678) == hash_phone(912345678.0) == raw   # number read from CSV, leading 0 lost
    assert hash_phone(float("nan")) is None


def test_phone_numbers_in_ad_text_are_redacted():
    from src.recsys.prepare import PHONE_IN_TEXT, redact_phones
    t = "Phòng 25m2 giá 3.500.000, LH/Zalo 0912.345.678 hoặc +84 912 345 678, tầng 3"
    assert redact_phones(t) == "Phòng 25m2 giá 3.500.000, LH/Zalo [SĐT ẩn] hoặc [SĐT ẩn], tầng 3"
    d = pd.read_csv("data/unified_hanoi_rentals_dedup.csv", low_memory=False, dtype=str)
    assert not d.description.fillna("").str.contains(PHONE_IN_TEXT).any()


def test_prepared_data_holds_no_raw_phone():
    d = pd.read_csv("data/unified_hanoi_rentals_dedup.csv", low_memory=False, dtype={"contact_phone": str})
    v = d.contact_phone.dropna()
    assert v.str.fullmatch(r"[0-9a-f]{16}|[0-9a-f]{64}").all()
    assert "contact_name" not in d


def test_prepared_data_ids_and_types_are_clean():
    from src.clean.sample_schema import canonical_house_type
    d = pd.read_csv("data/unified_hanoi_rentals_dedup.csv", low_memory=False, dtype={"listing_id": str})
    assert d.listing_id.is_unique                      # votes and duplicate_of join on it
    types = d.house_type.dropna()
    assert (types.map(canonical_house_type) == types).all()   # one spelling per type
    from src.clean.sample_schema import short_district
    dist = d.district.dropna()
    assert (dist.map(short_district) == dist).all()           # "Cầu Giấy", never "Quận Cầu Giấy" or "Chưa rõ"


def test_price_model_predictions_are_out_of_fold():
    rng = np.random.default_rng(0)
    n = 300
    d = pd.DataFrame({"listing_id": [f"x{i}" for i in range(n)], "title": "phòng", "house_type": "Phòng trọ",
                      "district": rng.choice(["A", "B"], n), "platform": "P", "area_m2": rng.uniform(15, 40, n),
                      "price_vnd": 0.0, "duplicate_of": None,
                      **{a: rng.integers(0, 2, n) for a in price_model.AMENITIES},
                      **{c: rng.uniform(0, 10, n) for c in price_model.DIST}})
    d["price_vnd"] = d.area_m2 * 120_000 * rng.uniform(0.9, 1.1, n)
    a = price_model.enrich(d, save=False)
    d2 = d.copy()
    d2.loc[0, "price_vnd"] *= 50   # a crazy price for one room must not move its own fair price
    b = price_model.enrich(d2, save=False)
    assert abs(a.fair_price[0] - b.fair_price[0]) / a.fair_price[0] < 0.05
    assert b.value_pct[0] > 1000


def test_own_price_does_not_leak_through_missing_area():
    rng = np.random.default_rng(0)
    n = 300
    area = rng.uniform(15, 40, n)
    d = pd.DataFrame({"listing_id": [f"x{i}" for i in range(n)], "title": "phòng", "house_type": "Phòng trọ",
                      "district": rng.choice(["A", "B"], n), "platform": "P", "area_m2": area,
                      "price_vnd": area * 120_000 * rng.uniform(0.9, 1.1, n), "duplicate_of": None,
                      **{a: rng.integers(0, 2, n) for a in price_model.AMENITIES},
                      **{c: rng.uniform(0, 10, n) for c in price_model.DIST}})
    d.loc[d.index % 2 == 0, "area_m2"] = np.nan   # half the rooms state no area, as in the real data
    a = price_model.enrich(d, save=False)
    d2 = d.copy()
    d2.loc[0, "price_vnd"] *= 3                    # row 0 has no stated area
    b = price_model.enrich(d2, save=False)
    assert a.fair_price[0] == b.fair_price[0]      # its own price must not reach its fair price via area_est


def test_cluster_ci_brackets_the_mean_and_signs_a_clear_gain():
    rng = np.random.default_rng(0)
    a = rng.uniform(0, 1, 400)
    groups = np.repeat(np.arange(100), 4)
    ci = price_model.cluster_ci(a, a + 0.5, groups)
    assert ci["a"][0] < a.mean() < ci["a"][1]
    assert ci["diff"] == [-0.5, -0.5]            # a always 0.5 lower: no uncertainty in the difference
    noisy = price_model.cluster_ci(a, a + rng.normal(0, 1, 400), groups)
    assert noisy["diff"][0] < 0 < noisy["diff"][1]   # no real gain: the interval spans zero


def test_cv_groups_keep_one_poster_and_one_building_together():
    d = pd.DataFrame({"contact_phone": ["aaaa", "aaaa", None, None, None],
                      "latitude": [21.0, 21.2, 21.03001, 21.03002, 21.1],
                      "longitude": [105.8, 105.9, 105.85001, 105.85002, 105.7]})
    g = price_model.cv_groups(d)
    assert g[0] == g[1]            # same poster, far apart
    assert g[2] == g[3] != g[4]    # a few metres apart vs another place


def test_feedback_round_trip_and_ltr(tmp_path):
    db = tmp_path / "fb.sqlite"
    rng = np.random.default_rng(1)
    for s in range(6):
        rows = pd.DataFrame({"listing_id": [f"l{i}" for i in range(20)], "rank": range(1, 21), "score": 0.5,
                             "s_price": rng.random(20), "s_value": rng.random(20), "s_dist": rng.random(20),
                             "s_amenity": rng.random(20), "price_vnd": 3e6})
        feedback.log(f"s{s}", "q", rows, "impression", db=db)
        up, down = rows[rows.s_value > 0.5], rows[rows.s_value <= 0.5]   # these users only care about value
        feedback.log(f"s{s}", "q", up, "up", db=db)
        feedback.log(f"s{s}", "q", down, "down", db=db)
    feedback.log("s0", "q", up.head(1), "down", db=db)   # changing a vote replaces it
    assert feedback.votes("s0", "q", db=db)[up.listing_id.iloc[0]] == "down"
    rep, w = ltr.evaluate(ltr.labelled(feedback.events(db=db)))
    assert rep["labels"] == 120 and max(w, key=w.get) == "value"
    assert rep["learned_cv"]["ndcg@10"] >= rep["hand"]["ndcg@10"]
    assert {"nearest_first", "price_plus_distance"} <= set(rep)
    c = rep["coef_std"]
    assert c["value"]["lo"] > 0 and c["value"]["coef"] > abs(c["price"]["coef"])   # signed, with an interval


def test_similar_rooms_and_text_search():
    d = load()
    idx = Index(d)
    sample = d[d.title.str.contains("gác xép", case=False, na=False)].listing_id.iloc[0]
    assert sample not in idx.similar(sample, k=5)
    s = idx.text_scores("phòng có gác xép", d.listing_id.head(500).tolist())
    top = d.head(500).iloc[np.argsort(-s)[:5]]
    assert top.title.str.contains("gác", case=False, na=False).any() or \
        top.description.str.contains("gác", case=False, na=False).any()


def test_ml_ranker_switch(tmp_path, monkeypatch):
    import json

    from src.recsys import recommend as rec
    path = tmp_path / "w.json"
    monkeypatch.setattr(rec, "LTR_WEIGHTS", path)
    assert rec.ranker_info() is None and rec.active_weights("ml") == rec.WEIGHTS   # nothing published: hand-set
    learned = {"price": 0.5, "value": 0.0, "distance": 0.5, "amenity": 0.0, "q_not_sublet": 0.0}
    path.write_text(json.dumps({"weights": learned, "source": "test"}))
    assert rec.active_weights("ml") == learned and rec.active_weights("hand") == rec.WEIGHTS
    d = load()
    a = recommend(d, 4_000_000, ["Cầu Giấy"], top=30, ranker="ml")
    b = recommend(d, 4_000_000, ["Cầu Giấy"], top=30, ranker="hand")
    assert list(a.listing_id) != list(b.listing_id)   # the two rankers really differ


def test_wilson_interval_matches_known_values():
    from src.recsys.report_numbers import wilson
    assert wilson(25, 25) == [86.7, 100.0] and wilson(0, 8) == [0.0, 32.4] and wilson(24, 25) == [80.5, 99.3]


def test_per_search_handles_several_searches_per_session():
    rng = np.random.default_rng(3)
    rows = []
    for s in range(3):
        for q in ("qa", "qb"):          # two searches in one session
            for i in range(12):
                rows.append({"session": f"s{s}", "query": q, "listing_id": f"{q}{i}", "label": int(rng.random() > 0.4),
                             "price_vnd": 3e6, **{p: rng.random() for p in feedback.PARTS},
                             **{k: 1.0 for k in ltr.QUALITY}})
    per = ltr.per_search(pd.DataFrame(rows))
    assert per.search.is_unique and len(per) == 6 and per.random.notna().all()


def test_usual_price_band_always_contains_the_fair_price():
    lo, hi = price_model.band_around(np.array([1.0, 1.0]), np.array([0.8, 1.2]), np.array([1.0, 1.0]), np.array([1.3, 0.9]))
    assert (lo <= 1.0).all() and (hi >= 1.0).all()            # crossing quantiles are clipped
    d = pd.read_csv("data/unified_hanoi_rentals_dedup.csv", low_memory=False)
    x = d[d.fair_price.notna()]
    assert ((x.fair_lo <= x.fair_price) & (x.fair_price <= x.fair_hi)).all()
    assert not ((x.price_vnd < x.fair_lo) & (x.value_pct > 0)).any()   # never "cheaper by -x%"
    assert not ((x.price_vnd > x.fair_hi) & (x.value_pct < 0)).any()
    from src.clean.sample_schema import coordinate_issues
    assert not (coordinate_issues(d.latitude, d.longitude) == "outside_hanoi").any()   # no placeholder points


def test_conformal_band_reaches_its_target_coverage():
    rng = np.random.default_rng(0)
    n = 2000
    y = rng.normal(0, 1, n)
    center = np.zeros(n)
    lo, hi = center - 0.3, center + 0.3            # far too narrow: covers ~24%
    folds = list(price_model._splits(n, None))
    new_lo, new_hi, qs = price_model.conformal_band(lo, hi, y, center, folds, coverage=0.8)
    cover = ((y >= new_lo) & (y <= new_hi)).mean()
    assert 0.77 <= cover <= 0.83 and all(q > 0 for q in qs)
    assert (new_lo <= center).all() and (new_hi >= center).all()
