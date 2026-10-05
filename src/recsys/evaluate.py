"""Offline evaluation on synthetic personas (no ground-truth ratings exist).

    python -m src.recsys.evaluate        # writes docs/RECSYS_EVAL.md + data/recsys_eval_labels.csv

Compares weight settings on behavioural metrics, plus a baseline that just sorts by price.
These metrics describe what each setting surfaces; they do not prove one is "better" --
the hand-labelling sheet (data/recsys_eval_labels.csv) is for that.
"""
import numpy as np
import pandas as pd

from src.recsys.recommend import WEIGHTS, load, recommend

M = 1_000_000
# (name, kwargs for recommend)
PERSONAS = [
    ("SV NEU rẻ", dict(budget=2.5 * M, university="NEU")),
    ("SV NEU thoải mái", dict(budget=4 * M, university="NEU", need=["air_conditioner", "water_heater"])),
    ("SV TMU", dict(budget=3 * M, university="TMU", max_uni_km=2)),
    ("SV HOU", dict(budget=3 * M, university="HOU")),
    ("SV UTC", dict(budget=3.5 * M, university="UTC", need=["air_conditioner"])),
    ("SV PTIT", dict(budget=3 * M, university="PTIT", min_area=18)),
    ("SV Thăng Long", dict(budget=3 * M, university="Thăng Long")),
    ("SV HANU", dict(budget=3.5 * M, university="HANU", need=["washing_machine"])),
    ("SV VNU", dict(budget=3 * M, university="VNU")),
    ("SV AJC", dict(budget=2.5 * M, university="AJC", min_area=15)),
    ("Đi làm Cầu Giấy", dict(budget=5 * M, districts=["Cầu Giấy"], need=["air_conditioner", "water_heater"])),
    ("Đi làm Đống Đa metro", dict(budget=5 * M, districts=["Đống Đa"], max_metro_km=1.5)),
    ("Đi làm Thanh Xuân", dict(budget=4.5 * M, districts=["Thanh Xuân"], min_area=20)),
    ("Studio Ba Đình", dict(budget=7 * M, districts=["Ba Đình"], house_type="Studio")),
    ("Studio Cầu Giấy", dict(budget=8 * M, districts=["Cầu Giấy"], house_type="Studio", need=["washing_machine"])),
    ("Cặp đôi Hà Đông", dict(budget=4 * M, districts=["Hà Đông"], min_area=25)),
    ("Nuôi thú cưng", dict(budget=6 * M, need=["pet_allowed"])),
    ("Cần thang máy", dict(budget=7 * M, need=["elevator"], min_area=25)),
    ("Ngân sách rất thấp", dict(budget=1.5 * M)),
    ("Ngân sách cao", dict(budget=12 * M, need=["air_conditioner", "elevator"])),
]
CONFIGS = {
    "baseline: rẻ nhất": {"price": 1, "value": 0, "distance": 0, "amenity": 0},
    "mặc định 30/25/25/20": WEIGHTS,
    "nghiêng giá trị": {"price": .15, "value": .5, "distance": .2, "amenity": .15},
    "nghiêng khoảng cách": {"price": .2, "value": .2, "distance": .5, "amenity": .1},
    "đều 25 mỗi mục": {"price": .25, "value": .25, "distance": .25, "amenity": .25},
}
TOP = 10
INCLUDE_SHARED = False  # True reproduces the pre-fix run (shared ads swamped the top)
from src.recsys.recommend import SHARED_RE as SHARED  # noqa: E402


def metrics(r, budget, by_uni):
    dist = r.distance_to_nearest_university_km if by_uni else r.distance_to_center_km
    return {
        "n": len(r),
        "giá/ngân sách": (r.price_vnd / budget).mean(),
        "% giá hời": r.market_value_tier.fillna("").str.startswith("Giá hời").mean(),
        "% ở ghép": r.title.str.contains(SHARED, case=False).mean(),
        "km TB": dist.mean(),
        "tiện nghi TB": r.amenity_count.mean(),
        "m² TB": r.area_est.mean(),
        "% ước lượng m²": r.area_imputed.mean(),
        "số quận": r.district.nunique(),
        "số nguồn": r.platform.nunique(),
    }


def main():
    d = load()
    ids = d.set_index("listing_id")
    rows, labels = [], []
    for cname, w in CONFIGS.items():
        for pname, kw in PERSONAS:
            r = recommend(d, top=TOP, weights=w, include_shared=INCLUDE_SHARED, **kw)
            if r.empty:
                rows.append({"config": cname, "persona": pname, "n": 0})
                continue
            r = r.join(ids[["amenity_count", "distance_to_center_km"]], on="listing_id")
            rows.append({"config": cname, "persona": pname,
                         **metrics(r, kw["budget"], bool(kw.get("university")))})
            if cname == "mặc định 30/25/25/20" and pname in [p[0] for p in PERSONAS[::4]]:
                labels += [{"persona": pname, "rank": i, "listing_id": x.listing_id, "title": x.title,
                            "price_vnd": x.price_vnd, "listing_url": x.listing_url, "rating_1_5": ""}
                           for i, x in enumerate(r.head(5).itertuples(), 1)]
    df = pd.DataFrame(rows)
    lab = pd.DataFrame(labels)
    try:  # keep ratings already entered for the same (persona, listing)
        old = pd.read_csv("data/recsys_eval_labels.csv").dropna(subset=["rating_1_5"])
        lab = lab.drop(columns="rating_1_5").merge(
            old[["persona", "listing_id", "rating_1_5"]], how="left", on=["persona", "listing_id"])
    except FileNotFoundError:
        pass
    lab.to_csv("data/recsys_eval_labels.csv", index=False, encoding="utf-8-sig")
    summ = df.groupby("config", sort=False).agg(
        persona_du_n=("n", lambda s: f"{(s >= TOP).sum()}/{len(s)}"),
        **{c: (c, "mean") for c in df.columns if c not in ("config", "persona", "n")})
    short = df[df.n < TOP][["persona", "n"]].drop_duplicates()
    with open("docs/RECSYS_EVAL.md", "w", encoding="utf-8") as f:
        f.write(f"# Đánh giá recommender bằng persona\n\n{len(PERSONAS)} persona × {len(CONFIGS)} cấu hình trọng số, top-{TOP}.\n"
                "Trung bình trên các persona có kết quả. 'persona_du_n' = số persona nhận đủ 10 kết quả.\n\n")
        f.write(summ.round(2).to_markdown() + "\n\n")
        f.write("Persona không đủ 10 kết quả: " + (", ".join(f"{a} ({b})" for a, b in short.values) or "không có") + "\n")
    print(summ.round(2).to_string())
    print(short.to_string(index=False))


if __name__ == "__main__":
    main()
