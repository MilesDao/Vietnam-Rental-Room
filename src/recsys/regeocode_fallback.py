"""Repair Phongtro123 rows that were all given one fallback coordinate.

    python -m src.recsys.regeocode_fallback     # ~35 Nominatim requests, cached

Root cause: the point (21.028511, 105.804817) -- which is also UTC's campus -- was assigned to rows
whose post-2025 ward name (Thanh Liệt, Hồng Hà, Trung Giã, ...) had no centroid in the pipeline's
table, so they looked "0.11 km from UTC" and "in Đống Đa". Here each such ward is geocoded once
with the project's cached Nominatim client (<= 1 request/s), and the rows get that ward's centroid,
the old district containing it (data/hanoi_districts.geojson) and recomputed distance features.
Rows whose address names no ward keep NaN coordinates. Output: data/unified_hanoi_rentals_geofixed.csv.

Coordinates are ward-level, not rooftop. "© OpenStreetMap contributors" must be credited wherever
they are published. value_residual_pct / market_value_tier are NOT recomputed (they depend on the
district of the old fallback point for ~530 rows); see docs/RECSYS_UPDATE_REPORT.md.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import Point, shape

from src.geo.address import area_candidate, fold
from src.geo.nominatim import ATTRIBUTION, NominatimGeocoder
from src.recsys.ref_points import HANOI_CENTER, METRO_STATIONS, UNIVERSITIES

SRC, OUT = Path("data/unified_hanoi_rentals.csv"), Path("data/unified_hanoi_rentals_geofixed.csv")
CACHE = Path("data/external/nominatim_cache.sqlite")
GEOJSON = Path("data/hanoi_districts.geojson")
MIN_WARDS = 5       # a point shared by listings from >= 5 different address wards is a fallback
WARD_RE = r"((?:Phường|Xã|Thị trấn) [^,]+)"
PROP = {"distance_to_nearest_metro_km", "metro_proximity_tier", "university_proximity_tier"}


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 12742.0 * np.arcsin(np.sqrt(a))


def nearest(lat, lon, points, key):
    """Index of the nearest point (same flat-earth ranking the pipeline used) and haversine km to it."""
    pl, pn = np.array([p[key[0]] for p in points]), np.array([p[key[1]] for p in points])
    idx = np.argmin((lat - pl) ** 2 + ((lon - pn) * np.cos(np.radians(21.0))) ** 2)
    return idx, haversine(lat, lon, pl[idx], pn[idx])


def tier(d, far):
    return ("< 500m (Đi bộ dễ dàng)" if d <= 0.5 else "500m - 1km (Đi bộ vừa)" if d <= 1.0
            else "1km - 2km (Xe đạp / Bus)" if d <= 2.0 else far)


def district_of(lat, lon, polys):
    pt = Point(lon, lat)
    return next((name for name, poly in polys if poly.contains(pt)), np.nan)


def load_polys():
    feats = json.loads(GEOJSON.read_text(encoding="utf-8"))["features"]
    return [(f["properties"]["NAME_2"], shape(f["geometry"])) for f in feats]


def fallback_mask(d):
    aw = d.address.str.extract(WARD_RE)[0]
    return aw.groupby([d.latitude, d.longitude]).transform("nunique") >= MIN_WARDS, aw


def main():
    d = pd.read_csv(SRC, low_memory=False)
    bad, aw = fallback_mask(d)
    wards = sorted(aw[bad].dropna().unique())
    print(f"{bad.sum()} fallback rows, {len(wards)} distinct wards to geocode")
    geo = NominatimGeocoder(CACHE, max_requests=len(wards) + 10)
    cent = {}
    try:
        for w in wards:
            r, _ = geo.geocode([area_candidate(w)])
            if r:
                cent[w] = (r.lat, r.lon)
    finally:
        geo.close()
    print(f"geocoded {len(cent)}/{len(wards)} ({geo.n_requests} requests, {geo.n_cache_hits} cache hits)")

    # GADM district names have no spaces ("BaĐình"): match on folded, space-free names
    polys = [(fold(n).replace(" ", ""), p) for n, p in load_polys()]
    by_fold = {fold(x).replace(" ", ""): x for x in d.district.dropna().unique()}
    dist_cols = [c for c in d if c.startswith("distance_to_") or c.startswith("nearest_") or c in PROP]
    d["geo_source"] = np.where(bad, "ward_centroid_nominatim", "")
    d.loc[bad, ["latitude", "longitude", "district", "ward"] + dist_cols] = np.nan
    for i in d.index[bad]:
        w = aw[i]
        if w not in cent:
            continue
        lat, lon = cent[w]
        dname = district_of(lat, lon, polys)
        d.loc[i, ["latitude", "longitude"]] = lat, lon
        d.loc[i, "district"] = by_fold.get(dname, np.nan) if isinstance(dname, str) else np.nan
        d.loc[i, "ward"] = w.split(" ", 1)[1] if not w.startswith("Thị trấn") else w[9:]
        d.loc[i, "distance_to_center_km"] = round(haversine(lat, lon, *HANOI_CENTER), 2)
        m, md = nearest(lat, lon, METRO_STATIONS, ("lat", "lng"))
        u, ud = nearest(lat, lon, UNIVERSITIES, ("lat", "lng"))
        d.loc[i, ["distance_to_nearest_metro_km", "nearest_metro_station"]] = round(md, 2), METRO_STATIONS[m]["name"]
        d.loc[i, "metro_proximity_tier"] = tier(md, "> 2km (Cách xa metro)")
        d.loc[i, ["distance_to_nearest_university_km", "nearest_university", "nearest_university_cluster"]] = (
            round(ud, 2), UNIVERSITIES[u]["name"], UNIVERSITIES[u]["cluster"])
        d.loc[i, "university_proximity_tier"] = tier(ud, "> 2km (Khu vực ngoài SV)")
    d.loc[bad & d.latitude.isna(), ["metro_proximity_tier", "university_proximity_tier"]] = "Không rõ tọa độ"
    d.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"wrote {OUT}; {bad.sum() - d.latitude[bad].isna().sum()} rows regained coordinates. {ATTRIBUTION}")


if __name__ == "__main__":
    main()
