"""How far can the coordinates be trusted? Writes docs/report_numbers.json["geo"].

1. Centre: the reference point of `distance_to_center_km` and how much the choice matters (alternative centres).
2. Polygon check: does each room's point fall in the district polygon (GADM, independent of every geocoder and
   platform) that matches its stated district? Per platform. The district label was partly derived from the point,
   so this is a plausibility check, not a proof of rooftop accuracy.
3. Precision: share of located rooms whose exact coordinate is shared by >= 5 rooms (a ward or district centroid,
   not a building) and the ward-centroid offset of Facebook's geocodes.

    python -m src.recsys.geo_validation
"""
import json
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from src.recsys.ref_points import HANOI_CENTER
from src.recsys.regeocode_fallback import haversine

ROOT = Path(__file__).resolve().parents[2]
NUMS = ROOT / "docs" / "report_numbers.json"
ALT_CENTRES = {"Ba Dinh Square": (21.0368, 105.8342), "Trang Tien / Dong Da": (21.0245, 105.8412),
               "Hanoi geographic mean": None}   # None -> mean of all located rooms


def norm(s):
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().replace("đ", "d").replace(" ", "").replace("quan", "").replace("huyen", "").replace("thixa", "")


def main():
    d = pd.read_csv(ROOT / "data" / "unified_hanoi_rentals_dedup.csv", low_memory=False)
    d = d[d.duplicate_of.isna() & d.latitude.notna()].copy()
    out = {"n_located": int(len(d)), "centre": {"lat": HANOI_CENTER[0], "lon": HANOI_CENTER[1]}}

    # 1. centre sensitivity
    own = haversine(d.latitude.values, d.longitude.values, *HANOI_CENTER)
    out["centre_recomputed_matches_stored"] = bool(np.allclose(own, d.distance_to_center_km, atol=0.01, equal_nan=True))
    out["median_km"] = round(float(np.median(own)), 2)
    sens = {}
    for name, c in ALT_CENTRES.items():
        c = c or (float(d.latitude.mean()), float(d.longitude.mean()))
        alt = haversine(d.latitude.values, d.longitude.values, *c)
        sens[name] = {"lat": round(c[0], 4), "lon": round(c[1], 4), "pearson_with_main": round(float(np.corrcoef(alt, own)[0, 1]), 3),
                      "median_shift_km": round(float(np.median(np.abs(alt - own))), 2)}
    out["centre_sensitivity"] = sens
    p = d[d.price_vnd.notna()]
    out["spearman_rent_vs_centre"] = round(float(spearmanr(p.price_vnd, haversine(p.latitude.values, p.longitude.values, *HANOI_CENTER))[0]), 3)

    # 2. polygon check
    g = json.load(open(ROOT / "data" / "hanoi_districts.geojson", encoding="utf-8"))
    polys = [shape(f["geometry"]) for f in g["features"]]
    names = [norm(f["properties"]["NAME_2"]) for f in g["features"]]
    tree = STRtree(polys)

    def where(la, lo):
        pt = Point(lo, la)
        for i in tree.query(pt):
            if polys[i].contains(pt):
                return names[i]
        return None

    d["poly"] = [where(a, b) for a, b in zip(d.latitude, d.longitude)]
    out["outside_hanoi_polygons"] = int(d.poly.isna().sum())
    k = d[d.poly.notna() & d.district.notna() & (d.district != "Chưa rõ")].copy()
    k["ok"] = k.poly == k.district.map(norm)
    out["district_agreement_pct"] = round(float(k.ok.mean() * 100), 1)
    out["district_agreement_n"] = int(len(k))
    out["district_agreement_by_platform"] = {p: round(float(v * 100), 1) for p, v in k.groupby("platform").ok.mean().items()}

    # 3. precision
    key = d.latitude.round(5).astype(str) + "," + d.longitude.round(5).astype(str)
    d["shared"] = key.map(key.value_counts()) >= 5
    out["shared_coordinate_pct"] = round(float(d.shared.mean() * 100), 1)
    out["shared_coordinate_pct_by_platform"] = {p: round(float(v * 100), 1) for p, v in d.groupby("platform").shared.mean().items()}
    fb = d.distance_to_ward_centroid_km.dropna()
    out["facebook_median_km_to_ward_centroid"] = round(float(fb.median()), 2)

    nums = json.loads(NUMS.read_text(encoding="utf-8"))
    nums["geo"] = out
    NUMS.write_text(json.dumps(nums, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
