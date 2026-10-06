"""Swap freshly re-crawled platforms into the unified Hanoi dataset.

    python -m src.pipelines.merge_fresh [--fresh data/interim/recrawl_2026-10]

Reads each source's fresh export, maps it to the unified columns, recomputes what the recommender needs
that the raw exports lack (district from coordinates, distances to centre/metro/university, amenity
count, a rough living-cost estimate), drops those platforms' old rows from data/unified_hanoi_rentals.csv
and writes data/unified_hanoi_rentals_fresh.csv. Platforms with no fresh file (Facebook ...) are kept as is.
Hanoi only. Links/images are normalised with src.clean.link_check; rows with a non-permalink link keep the
row but get an empty listing_url.
"""
import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.clean.link_check import is_permalink, parse_images
from src.export.text_features import extract_amenity_features, extract_utility_prices, get_amenities_list
from src.geo.address import fold
from src.recsys.prepare import hash_phone
from src.recsys.ref_points import HANOI_CENTER, METRO_STATIONS, UNIVERSITIES
from src.recsys.regeocode_fallback import district_of, haversine, load_polys, nearest, tier

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "data/unified_hanoi_rentals.csv"
NEW = ROOT / "data/unified_hanoi_rentals_fresh.csv"
FLAGS = ["air_conditioner", "water_heater", "refrigerator", "washing_machine", "elevator", "balcony_window",
         "fire_safety", "pet_allowed"]
UTILS = ["electric_price", "water_price", "wifi_price", "other_utilities_price", "parking_fee"]
FALLBACK = (21.028511, 105.804817)   # placeholder coordinate the phongtro123 geocoder used for unmatched wards
MIN_PRICE, MAX_PRICE = 500_000, 50_000_000   # VND/month; outside this is a typo, a per-night stay or a shop
NOT_A_ROOM = re.compile(r"^(cho thuê\s+)?(văn phòng|mặt bằng|cửa hàng|kho |nhà xưởng)", re.I)
PREFIX = re.compile(r"^(quận|huyện|thị xã|thành phố)\s+", re.I)
WARD_PREFIX = re.compile(r"^(phường|xã|thị trấn)\s+", re.I)


def _posted(value):
    """Anything date-like -> 'dd/mm/yyyy' (what recsys.prepare.add_dates reads)."""
    m = re.search(r"\d{2}/\d{2}/\d{4}", str(value))   # already dd/mm/yyyy, e.g. "Thứ 4, 15:44 30/09/2026"
    if m:
        return m.group(0)
    t = pd.to_datetime(value, errors="coerce", utc=True)
    return t.strftime("%d/%m/%Y") if pd.notna(t) else None


def _text_features(d):
    """Amenity flags / utility snippets from the text, except where the source export already has them."""
    extra = d["amenities_raw"] if "amenities_raw" in d else ""
    text = d.title.fillna("") + ". " + d.description.fillna("") + ". " + extra
    feats = text.map(extract_amenity_features)
    for f in FLAGS:
        if f not in d:
            d[f] = feats.map(lambda x, f=f: int(x[f]))
    d[FLAGS] = d[FLAGS].fillna(0).astype(int)
    if "amenities_list" not in d:
        d["amenities_list"] = d[FLAGS].apply(lambda r: get_amenities_list({f: bool(r[f]) for f in FLAGS}), axis=1)
    utils = text.map(extract_utility_prices)
    for k in UTILS:
        if k not in d:
            d[k] = utils.map(lambda u, k=k: u.get(k) or np.nan)
    return d


PHONE_COLS = {c: str for c in ("contact_phone", "contact_zalo", "phone_number", "alternative_phone")}


def mogi(p):
    d = pd.read_csv(p, low_memory=False, dtype=PHONE_COLS)
    d["listing_id"] = d.listing_id.astype(str).map(lambda i: i if i.startswith("mogi_") else "mogi_" + i)
    d["description"] = ""
    return d


def alonhadat(p):
    d = pd.read_csv(p, low_memory=False, dtype=PHONE_COLS)
    d["district"] = d.district.str.replace(PREFIX, "", regex=True)
    d["ward"] = d.ward.fillna("").str.replace(WARD_PREFIX, "", regex=True)
    d["listing_id"] = d.listing_id.astype(str).map(lambda i: i if i.startswith("alonhadat_") else "alonhadat_" + i)
    d["description"] = ""
    return d


def phongtro123(p):
    d = pd.read_csv(p, low_memory=False, dtype=PHONE_COLS)
    d = d[d.city.fillna("Hà Nội").str.contains("Hà Nội", case=False)]
    d["listing_url"] = d.url
    d["address"] = d.address_raw
    d["contact_phone"] = d.phone_number
    d["image_urls"] = d.image_urls   # already a JSON list
    return d


def nhatot(p):
    d = pd.read_csv(p, low_memory=False, dtype=PHONE_COLS)
    d["district"] = d.district.str.replace(PREFIX, "", regex=True)
    d["ward"] = d.ward.fillna("").str.replace(WARD_PREFIX, "", regex=True)
    d["listing_id"] = d.listing_id.astype(str)
    return d


def rencity(p):
    d = pd.read_csv(p, low_memory=False, dtype=PHONE_COLS)
    out = pd.DataFrame({
        "listing_id": "RC_" + d.id.astype(str), "title": d.title,
        "description": "", "ward": d.wards_name.fillna("").str.replace(WARD_PREFIX, "", regex=True),
        "address": d.address_detail.fillna("") + ", " + d.wards_name.fillna("") + ", Hà Nội",
        "price_vnd": d.min_money_vnd, "area_m2": d.area_m2, "house_type": "Phòng trọ",
        "latitude": d.latitude, "longitude": d.longitude, "image_urls": d.image_urls,
        "listing_url": d.post_url, "posted_at_raw": d.updated_at, "contact_phone": np.nan,
    })
    return out[~out.title.fillna("").str.match(NOT_A_ROOM)]


def yourhome(p):
    d = pd.read_csv(p, low_memory=False, dtype={"contact_phone": str, "contact_zalo": str})
    d = d[(d.city == "ha-noi") & (d.room_type != "mbkd")]
    return pd.DataFrame({
        "listing_id": "YH_" + d.id.astype(str), "title": d.title,
        "description": d.description, "amenities_raw": d.amenities.fillna("") + ". " + d.utility_costs.fillna(""),
        "district": d.district, "address": d.location.fillna("") + ", " + d.district.fillna("") + ", Hà Nội",
        "price_vnd": d.price_vnd, "area_m2": d.area_m2, "house_type": d.room_type,
        "latitude": d.latitude, "longitude": d.longitude, "contact_phone": d.contact_phone,
        "image_urls": d.image_urls, "listing_url": d.post_url, "posted_at_raw": d.posted_date,
    })


ADAPTERS = {  # platform -> (fresh file name, adapter)
    "Mogi.vn": ("mogi.csv", mogi),
    "Alonhadat.vn": ("alonhadat.csv", alonhadat),
    "ChoTot.com": ("nhatot.csv", nhatot),
    "Phongtro123.com": ("phongtro123.csv", phongtro123),
    "Rencity.vn": ("rooms_rencity_hanoi.csv", rencity),
    "YourHome.top": ("rooms_ha-noi.csv", yourhome),
}


def clean_numbers(d):
    """0 / negative area is "unknown", not a room of 0 m2; a non-positive price is no listing at all."""
    d = d.copy()
    for c in ["latitude", "longitude", "price_vnd", "area_m2"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d.loc[d.area_m2 <= 0, "area_m2"] = np.nan
    room = ~d.title.fillna("").str.strip().str.match(NOT_A_ROOM)
    return d[d.price_vnd.between(MIN_PRICE, MAX_PRICE) & room]   # typos (2 VND, 300 M) and shops are not rooms


def fill_coords(d, old):
    """Rows with no coordinates (alonhadat) get the median point of old rows with the same district+ward
    (ward-level accuracy, no network). ponytail: ward centroid only; geocode the street if precision matters."""
    key = ["district", "ward"]
    if not set(key) <= set(d) or not (d.latitude.isna() | d.longitude.isna()).any():
        return d
    ref = old.dropna(subset=["latitude", "longitude"]).groupby(key)[["latitude", "longitude"]].median()
    miss = d.latitude.isna() | d.longitude.isna()
    pts = d.loc[miss, key].merge(ref, left_on=key, right_index=True, how="left")
    d.loc[miss, ["latitude", "longitude"]] = pts[["latitude", "longitude"]].values
    return d


def finish(d, platform, polys, district_names, old=None):
    """Common columns + everything derived from coordinates."""
    d = (d.drop_duplicates("listing_id") if "listing_id" in d else d).copy()   # API pages overlap (Rencity: 2 ads twice)
    d["platform"] = platform
    d["contact_phone"] = d.contact_phone.map(hash_phone) if "contact_phone" in d else np.nan   # no raw phones on disk
    d["contact_zalo"] = d.contact_phone
    d = d.drop(columns=["contact_name"], errors="ignore")
    d["city"] = "Hà Nội"
    d["source_file"] = "recrawl_2026-10"
    d["crawled_at"] = datetime.now().isoformat(timespec="seconds")
    for c in ["description", "title", "address", "ward", "house_type"]:
        d[c] = d[c].fillna("") if c in d else ""
    d = _text_features(d)
    d = clean_numbers(d)
    if old is not None:
        d = fill_coords(d, old)
    d = d[~((d.latitude.round(6) == FALLBACK[0]) & (d.longitude.round(6) == FALLBACK[1]))]   # phongtro123's "unknown ward" point
    d = d[d.price_vnd.notna() & d.latitude.notna()].copy()
    if "district" not in d or d.district.isna().any():   # Rencity: no district field -> polygon lookup
        by_fold = {fold(x).replace(" ", ""): x for x in district_names}
        look = [district_of(a, o, polys) for a, o in zip(d.latitude, d.longitude)]
        guess = pd.Series([by_fold.get(fold(x).replace(" ", "")) if isinstance(x, str) else np.nan for x in look],
                          index=d.index)
        d["district"] = d.district.fillna(guess) if "district" in d else guess
    d["district_raw"] = d.district
    d = d[d.district.notna()].copy()                       # outside the Hanoi polygons -> not Hanoi
    d["image_urls"] = d.image_urls.map(lambda v: json.dumps(parse_images(v), ensure_ascii=False))
    d["image_count"] = d.image_urls.map(lambda v: len(json.loads(v)))
    d["listing_url"] = [u if is_permalink(platform, u) else np.nan for u in d.listing_url]
    d["posted_at_raw"] = d.posted_at_raw.map(_posted) if "posted_at_raw" in d else None
    d["price_per_m2"] = (d.price_vnd / d.area_m2).round(1)
    d["amenity_count"] = d[FLAGS].sum(axis=1)
    d["distance_to_center_km"] = [round(haversine(a, o, *HANOI_CENTER), 2) for a, o in zip(d.latitude, d.longitude)]
    for name, pts, far, ncol in [("metro", METRO_STATIONS, "> 2km (Cách xa metro)", "nearest_metro_station"),
                                 ("university", UNIVERSITIES, "> 2km (Khu vực ngoài SV)", "nearest_university")]:
        res = [nearest(a, o, pts, ("lat", "lng")) for a, o in zip(d.latitude, d.longitude)]
        d[f"distance_to_nearest_{name}_km"] = [round(r[1], 2) for r in res]
        d[ncol] = [pts[r[0]]["name"] for r in res]
        d[f"{name}_proximity_tier"] = [tier(r[1], far) for r in res]
        if name == "university":
            d["nearest_university_cluster"] = [pts[r[0]]["cluster"] for r in res]
    return d.drop(columns=["amenities_raw"], errors="ignore")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", default=str(ROOT / "data/interim/recrawl_2026-10"))
    a = ap.parse_args()
    fresh = Path(a.fresh)
    old = pd.read_csv(OLD, low_memory=False, dtype=PHONE_COLS)
    polys = load_polys()
    names = old.district.dropna().unique()
    extra = (old.estimated_total_living_cost - old.price_vnd).median()
    parts, replaced = [], []
    for platform, (fname, adapter) in ADAPTERS.items():
        f = fresh / fname
        if not f.exists():
            print(f"{platform}: no fresh file {fname}, keeping old rows")
            continue
        d = finish(adapter(f), platform, polys, names, old)
        # ponytail: flat median add-on; the old cost formula is not in this repo. Refine if cost drives ranking.
        d["estimated_total_living_cost"] = d.price_vnd + extra
        print(f"{platform}: {len(d)} fresh Hanoi rows (old {int((old.platform == platform).sum())})")
        parts.append(d)
        replaced.append(platform)
    out = pd.concat([old[~old.platform.isin(replaced)], *parts], ignore_index=True)
    out.to_csv(NEW, index=False, encoding="utf-8-sig")
    print(f"wrote {NEW}: {len(out)} rows (replaced {replaced})")


if __name__ == "__main__":
    main()
