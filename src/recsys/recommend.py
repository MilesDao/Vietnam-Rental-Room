"""Content-based rental recommender: hard filters, then a weighted score.

    python -m src.recsys.recommend --budget 4000000 --district "Cầu Giấy" \
        --university TMU --need air_conditioner water_heater --top 10
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.clean.sample_schema import _specific_address_key

DATA = Path(__file__).resolve().parents[2] / "data/unified_hanoi_rentals_dedup.csv"  # python -m src.recsys.dedup_unified
AMENITIES = ["air_conditioner", "water_heater", "refrigerator", "washing_machine",
             "elevator", "balcony_window", "fire_safety", "pet_allowed"]
# ponytail: fixed weights, learn them from clicks/ratings if you ever collect any
WEIGHTS = {"price": 0.30, "value": 0.25, "distance": 0.25, "amenity": 0.20}
SHOW = ["listing_id", "platform", "title", "district", "ward", "price_vnd", "area_est", "area_imputed",
        "estimated_total_living_cost", "market_value_tier", "nearest_university",
        "distance_to_nearest_university_km", "distance_to_nearest_metro_km",
        "amenities_list", "listing_url", "score"]


def load(path=DATA):
    d = pd.read_csv(path, low_memory=False).drop_duplicates("listing_id")
    d = d[d.duplicate_of.isna()]  # one row per room across platforms
    return mark_shared(add_typical_price(impute_area(null_fallback_geo(d.dropna(subset=["price_vnd"])))))


def null_fallback_geo(d):
    """Blank coordinates (and what was derived from them) shared by listings from many wards.

    Phongtro123 rows whose post-2025 ward name had no crosswalk entry all got one fallback
    point (21.028511, 105.804817, "Láng Thượng"/Đống Đa) although their addresses name 35
    different wards. They then look "0.11 km from UTC" and "in Đống Đa".
    """
    d = d.copy()
    aw = d.address.str.extract(r"(?:Phường|Xã|Thị trấn) ([^,]+)")[0].str.strip()
    n_wards = aw.groupby([d.latitude, d.longitude]).transform("nunique")
    bad = n_wards >= 5
    cols = ["latitude", "longitude", "district", "ward"] + [c for c in d if c.startswith(("distance_to_", "nearest_")) or c.endswith("proximity_tier")]
    d.loc[bad, cols] = np.nan
    d["geo_suspect"] = bad
    return d


def impute_area(d):
    """Add area_est (= area_m2, else median of its house_type x price-quintile) and area_imputed.

    Holdout MAE on known areas: 7.8 m2 vs 10.5 m2 for the global median.
    Only used for scoring and display; the --min-area filter still uses the real area.
    """
    d = d.copy()
    keys = [d.house_type.fillna(""), pd.qcut(d.price_vnd, 5, labels=False, duplicates="drop")]
    med = d.groupby(keys).area_m2.transform("median")
    d["area_imputed"] = d.area_m2.isna()
    d["area_est"] = d.area_m2.fillna(med).fillna(d.area_m2.median())
    return d


# ponytail: keyword guess; homestay/sleep box/"1 người" ads price one bed, not the room
SHARED_RE = r"ghép|slot|giường|home ?stay|sleep ?box|1 người|/ ?người|\d ?/ ?ng\b|\bshare\b"
DORM_RE = r"ký túc xá|ktx"  # dorm beds cost ~1.2-1.9M; a 4.2M "Trọ Ký Túc Xá ..." with 40 m2 is a normal room


def add_typical_price(d):
    """typical_price = median rent of the same house_type x district (house_type alone if < 30 rows)."""
    d = d.copy()
    by_type = d.groupby("house_type").price_vnd.transform("median")
    grp = d.groupby(["house_type", "district"])
    d["typical_price"] = grp.price_vnd.transform("median").where(grp.price_vnd.transform("size") >= 30, by_type)
    d["typical_price"] = d.typical_price.fillna(d.price_vnd.median())
    return d


def price_score(price, typical, budget):
    """1 at the typical price, falling off for much cheaper rooms (usually a slot, a stub ad or
    a mislabelled price) and, more gently, towards the budget. Replaces 1 - price/budget, which
    made the cheapest ads win every query."""
    ref = np.minimum(typical, budget)
    cheap = np.minimum(price / ref, 1)
    dear = 1 - 0.5 * (price - ref) / np.maximum(budget - ref, 1)
    return np.where(price < ref, cheap, dear)


def mark_shared(d):
    """is_shared: per-bed ads (see SHARED_RE) and cheap dorm beds."""
    d = d.copy()
    t = d.title.fillna("")
    d["is_shared"] = t.str.contains(SHARED_RE, case=False) | (t.str.contains(DORM_RE, case=False) & (d.price_vnd < 2_500_000))
    return d


def _rank01(s):
    """0..1, higher = larger value; NaN -> neutral 0.5."""
    return s.rank(pct=True).fillna(0.5)


def recommend(d, budget, districts=(), min_area=None, need=(), university=None,
              max_uni_km=None, max_metro_km=None, house_type=None, top=10, weights=None, include_shared=False, per_building=1):
    m = d[d.price_vnd <= budget]
    if not include_shared:
        # shared-room ads price one slot but list the whole room's area, so they look like
        # -57% "bargains" (median value_residual_pct) and swamp the top of the ranking
        m = m[~m.is_shared]
    if districts:
        m = m[m.district.isin(districts)]
    if min_area:  # listings with unknown area are kept; they only lose nothing
        m = m[m.area_m2.isna() | (m.area_m2 >= min_area)]
    for a in need:
        m = m[m[a] == 1]
    if university:
        m = m[m.nearest_university.fillna("").str.contains(university, case=False, regex=False)]
    if max_uni_km:
        m = m[m.distance_to_nearest_university_km <= max_uni_km]
    if max_metro_km:
        m = m[m.distance_to_nearest_metro_km <= max_metro_km]
    if house_type:
        m = m[m.house_type.fillna("").str.contains(house_type, case=False, regex=False)]
    if m.empty:
        return m
    m = m.copy()
    s_price = price_score(m.price_vnd, m.typical_price, budget)
    # negative residual = cheaper than the model expects for that room
    # ponytail: rows without a residual fall back to rank of price per estimated m2 (mixes two
    # measures); fit the residual model on area_est if this matters
    s_value = 1 - _rank01(m.value_residual_pct).where(m.value_residual_pct.notna(), _rank01(m.price_vnd / m.area_est))
    dist = m.distance_to_nearest_university_km if university or max_uni_km \
        else m.distance_to_center_km
    s_dist = 1 - _rank01(dist)
    s_am = _rank01(m.amenity_count)
    w = weights or WEIGHTS
    m["score"] = (w["price"] * s_price + w["value"] * s_value
                  + w["distance"] * s_dist + w["amenity"] * s_am).round(3)
    m = m.sort_values("score", ascending=False)
    if per_building:
        # the same house/alley number in one district = same building: show its best rooms only.
        # Not merged in the data, since different units there can legitimately differ in price/area.
        key = m.district.fillna("") + "|" + m.address.map(_specific_address_key)
        m = m[(m.address.map(_specific_address_key) == "") | (m.groupby(key).cumcount() < per_building)]
    return m.head(top)[[c for c in SHOW if c in m]]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--budget", type=float, required=True, help="max rent, VND/month")
    p.add_argument("--district", nargs="*", default=[])
    p.add_argument("--min-area", type=float)
    p.add_argument("--need", nargs="*", default=[], choices=AMENITIES)
    p.add_argument("--university", help="substring, e.g. TMU, Thăng Long")
    p.add_argument("--max-uni-km", type=float)
    p.add_argument("--max-metro-km", type=float)
    p.add_argument("--house-type")
    p.add_argument("--include-shared", action="store_true", help="keep ở-ghép / slot ads")
    p.add_argument("--per-building", type=int, default=1, help="max rooms per house/alley number (0 = no cap)")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("-o", help="save results to CSV (utf-8-sig)")
    a = p.parse_args()
    r = recommend(load(), a.budget, a.district, a.min_area, a.need, a.university,
                  a.max_uni_km, a.max_metro_km, a.house_type, a.top, include_shared=a.include_shared, per_building=a.per_building)
    if r.empty:
        print("No listing matches those filters; loosen one.")
        return
    pd.set_option("display.width", 250, "display.max_colwidth", 40)
    print(r.drop(columns=["amenities_list", "listing_url"], errors="ignore").to_string(index=False))
    if a.o:
        r.to_csv(a.o, index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
