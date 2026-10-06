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


def test_prepared_data_holds_no_raw_phone():
    d = pd.read_csv("data/unified_hanoi_rentals_dedup.csv", low_memory=False, dtype={"contact_phone": str})
    v = d.contact_phone.dropna()
    assert v.str.fullmatch(r"[0-9a-f]{16}|[0-9a-f]{64}").all()
    assert "contact_name" not in d


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
