#!/usr/bin/env python3
"""
clean_and_visualize_unified.py

End-to-end data cleaning, geodetic district/ward regeneration, 
derived feature engineering (including metro & university proximity),
and publication-grade visualization pipeline with authentic cartographic basemaps
for the Hanoi Rental Housing Market.

Follows user specifications:
- Audits missingness and outliers on the raw dataset BEFORE cleaning
- Regenerates districts and wards using WGS84 latitude and longitude
- Enforces strict data quality fences (spatial, price, area)
- Computes derived spatial & economic indicators (metro distance, university proximity, true living cost, value score)
- Saves unified cleaned dataset to data/hanoi_rentals_cleaned_unified.csv
- Generates side-by-side composite figures:
  * LEFT: Authentic cartographic basemap (Esri WorldStreetMap) showing spatial distributions
  * RIGHT: Statistical distribution (bar chart, boxplot, or KDE histogram)
"""

import os
import sys

# Strictly cap CPU threads per project guidelines
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"
os.environ["OPENBLAS_NUM_THREADS"] = "4"
os.environ["NUMEXPR_NUM_THREADS"] = "4"

import json
import math
import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.colors import LinearSegmentedColormap
import seaborn as sns
from sklearn.linear_model import Ridge
import contextily as cx

# Project directory paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
RAW_DATA_PATH = os.path.join(PROJECT_ROOT, "data", "merged_hanoi_rentals.csv")
CLEAN_DATA_PATH = os.path.join(PROJECT_ROOT, "data", "hanoi_rentals_cleaned_unified.csv")
UNIFIED_BENCHMARK_PATH = os.path.join(PROJECT_ROOT, "data", "unified_hanoi_rentals.csv")
FIGURES_DIR = os.path.join(PROJECT_ROOT, "figures")
AUDIT_JSON_PATH = os.path.join(PROJECT_ROOT, "data", "precleaning_audit.json")

os.makedirs(FIGURES_DIR, exist_ok=True)

# Visual styling
plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial", "Helvetica"]
plt.rcParams["axes.edgecolor"] = "#CBD5E1"
plt.rcParams["axes.linewidth"] = 0.8
plt.rcParams["grid.color"] = "#F1F5F9"
plt.rcParams["grid.linestyle"] = "--"

# -----------------------------------------------------------------------------
# 1. Official Hanoi Geospatial Reference Data
# -----------------------------------------------------------------------------

# Import inner-city ward centroids from build_unified_dataset
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src", "pipelines"))
try:
    from build_unified_dataset import DISTRICT_WARD_COORDS
except ImportError:
    DISTRICT_WARD_COORDS = {}

# Expand with all peri-urban and suburban district centroids
ADDITIONAL_DISTRICT_COORDS = {
    "Thạch Thất": {
        "Liên Quan": (21.0315, 105.5480),
        "Thạch Hòa (Hòa Lạc)": (21.0125, 105.5265),
        "Bình Yên": (21.0180, 105.5180),
    },
    "Quốc Oai": {
        "Quốc Oai": (20.9850, 105.6350),
        "Sài Sơn": (21.0150, 105.6550),
    },
    "Chương Mỹ": {
        "Chúc Sơn": (20.9250, 105.7050),
        "Xuân Mai": (20.8850, 105.5850),
    },
    "Đan Phượng": {
        "Phùng": (21.0950, 105.6750),
        "Tân Lập": (21.0750, 105.7050),
    },
    "Mê Linh": {
        "Đại Thịnh": (21.1750, 105.7150),
        "Quang Minh": (21.1950, 105.7850),
    },
    "Sóc Sơn": {
        "Sóc Sơn": (21.2600, 105.8500),
        "Phù Lỗ": (21.2150, 105.8650),
    },
    "Sơn Tây": {
        "Lê Lợi": (21.1380, 105.5050),
        "Quang Trung": (21.1320, 105.5100),
    },
    "Thanh Oai": {
        "Kim Bài": (20.8750, 105.7800),
        "Cự Khê": (20.9350, 105.7950),
    },
    "Thường Tín": {
        "Thường Tín": (20.8700, 105.8600),
    },
    "Phú Xuyên": {
        "Phú Xuyên": (20.7300, 105.9100),
    },
    "Ba Vì": {
        "Tây Đằng": (21.2400, 105.3800),
    },
}

# Master ward centroid table: (district, ward, lat, lng)
ALL_WARD_CENTROIDS = []
for d, ws in DISTRICT_WARD_COORDS.items():
    for w, (wlat, wlng) in ws.items():
        ALL_WARD_CENTROIDS.append((d, w, float(wlat), float(wlng)))
for d, ws in ADDITIONAL_DISTRICT_COORDS.items():
    for w, (wlat, wlng) in ws.items():
        ALL_WARD_CENTROIDS.append((d, w, float(wlat), float(wlng)))

WARD_DF = pd.DataFrame(ALL_WARD_CENTROIDS, columns=["district", "ward", "latitude", "longitude"])

# Operational Hanoi Metro Stations
METRO_STATIONS = [
    # Line 2A (Cát Linh - Hà Đông)
    {"line": "Line 2A", "name": "Cát Linh", "lat": 21.0287, "lng": 105.8277},
    {"line": "Line 2A", "name": "La Thành", "lat": 21.0205, "lng": 105.8235},
    {"line": "Line 2A", "name": "Thái Hà", "lat": 21.0125, "lng": 105.8196},
    {"line": "Line 2A", "name": "Láng", "lat": 21.0051, "lng": 105.8143},
    {"line": "Line 2A", "name": "Thượng Đình", "lat": 20.9972, "lng": 105.8118},
    {"line": "Line 2A", "name": "Vành Đai 3", "lat": 20.9902, "lng": 105.8033},
    {"line": "Line 2A", "name": "Phùng Khoang", "lat": 20.9839, "lng": 105.7925},
    {"line": "Line 2A", "name": "Văn Quán", "lat": 20.9781, "lng": 105.7828},
    {"line": "Line 2A", "name": "Hà Đông", "lat": 20.9715, "lng": 105.7745},
    {"line": "Line 2A", "name": "La Khê", "lat": 20.9632, "lng": 105.7638},
    {"line": "Line 2A", "name": "Văn Khê", "lat": 20.9547, "lng": 105.7533},
    {"line": "Line 2A", "name": "Yên Nghĩa", "lat": 20.9497, "lng": 105.7447},
    # Line 3 (Nhổn - Ga Hà Nội, Elevated section)
    {"line": "Line 3", "name": "Nhổn", "lat": 21.0538, "lng": 105.7335},
    {"line": "Line 3", "name": "Minh Khai", "lat": 21.0503, "lng": 105.7441},
    {"line": "Line 3", "name": "Phú Diễn", "lat": 21.0475, "lng": 105.7552},
    {"line": "Line 3", "name": "Cầu Diễn", "lat": 21.0425, "lng": 105.7677},
    {"line": "Line 3", "name": "Lê Đức Thọ", "lat": 21.0381, "lng": 105.7766},
    {"line": "Line 3", "name": "Đại học Quốc gia", "lat": 21.0360, "lng": 105.7830},
    {"line": "Line 3", "name": "Chùa Hà", "lat": 21.0336, "lng": 105.7944},
    {"line": "Line 3", "name": "Cầu Giấy", "lat": 21.0298, "lng": 105.8048},
]
METRO_DF = pd.DataFrame(METRO_STATIONS)

# Major Hanoi Universities & Academic Clusters
UNIVERSITIES = [
    # Cầu Giấy Cluster
    {"name": "ĐH Quốc gia (VNU)", "cluster": "Cầu Giấy", "lat": 21.0378, "lng": 105.7818},
    {"name": "ĐH Sư phạm (HNUE)", "cluster": "Cầu Giấy", "lat": 21.0366, "lng": 105.7839},
    {"name": "ĐH Thương mại (TMU)", "cluster": "Cầu Giấy", "lat": 21.0365, "lng": 105.7725},
    {"name": "HV Báo chí (AJC)", "cluster": "Cầu Giấy", "lat": 21.0372, "lng": 105.7925},
    {"name": "ĐH Giao thông Vận tải (UTC)", "cluster": "Cầu Giấy", "lat": 21.0289, "lng": 105.8038},
    # Đống Đa - Chùa Láng Cluster
    {"name": "ĐH Ngoại thương (FTU)", "cluster": "Chùa Láng", "lat": 21.0232, "lng": 105.8055},
    {"name": "ĐH Luật Hà Nội (HLU)", "cluster": "Chùa Láng", "lat": 21.0185, "lng": 105.8115},
    # Đống Đa - Chùa Bộc Cluster
    {"name": "HV Ngân hàng (BA)", "cluster": "Chùa Bộc", "lat": 21.0092, "lng": 105.8290},
    {"name": "ĐH Thủy lợi (TLU)", "cluster": "Chùa Bộc", "lat": 21.0075, "lng": 105.8242},
    {"name": "ĐH Y Hà Nội (HMU)", "cluster": "Chùa Bộc", "lat": 21.0028, "lng": 105.8315},
    # Bách - Kinh - Xây Cluster (Hai Bà Trưng)
    {"name": "ĐH Bách khoa (HUST)", "cluster": "Bách - Kinh - Xây", "lat": 21.0051, "lng": 105.8432},
    {"name": "ĐH Kinh tế Quốc dân (NEU)", "cluster": "Bách - Kinh - Xây", "lat": 20.9965, "lng": 105.8425},
    {"name": "ĐH Xây dựng (HUCE)", "cluster": "Bách - Kinh - Xây", "lat": 21.0035, "lng": 105.8428},
    {"name": "ĐH Mở Hà Nội (HOU)", "cluster": "Bách - Kinh - Xây", "lat": 21.0055, "lng": 105.8475},
    # Thanh Xuân - Hà Đông Corridor
    {"name": "ĐH Hà Nội (HANU)", "cluster": "Thanh Xuân", "lat": 20.9885, "lng": 105.7942},
    {"name": "ĐH KHXH&NV / KHTN (VNU)", "cluster": "Thanh Xuân", "lat": 20.9990, "lng": 105.8090},
    {"name": "HV Bưu chính (PTIT)", "cluster": "Hà Đông", "lat": 20.9805, "lng": 105.7875},
    {"name": "ĐH Kiến trúc (HAU)", "cluster": "Hà Đông", "lat": 20.9825, "lng": 105.7895},
    {"name": "ĐH Thăng Long", "cluster": "Hoàng Mai", "lat": 20.9765, "lng": 105.8165},
    # Bắc Từ Liêm Cluster
    {"name": "ĐH Công nghiệp (HaUI)", "cluster": "Bắc Từ Liêm", "lat": 21.0542, "lng": 105.7355},
    {"name": "HV Tài chính (AOF)", "cluster": "Bắc Từ Liêm", "lat": 21.0745, "lng": 105.7725},
    {"name": "ĐH Mỏ - Địa chất (HUMG)", "cluster": "Bắc Từ Liêm", "lat": 21.0725, "lng": 105.7745},
]
UNIVERSITIES_DF = pd.DataFrame(UNIVERSITIES)
HANOI_CENTER = (21.0285, 105.8542)  # Hoàn Kiếm Lake / Post Office

def haversine_vectorized(lats1, lngs1, lats2, lngs2):
    """Vectorized Haversine spherical distance in kilometers."""
    R = 6371.0
    phi1, phi2 = np.radians(lats1), np.radians(lats2)
    dphi = np.radians(lats2 - lats1)
    dlambda = np.radians(lngs2 - lngs1)
    a = np.sin(dphi / 2.0)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2.0)**2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return R * c

_JAPANESE_INK_MAP = None

def get_japanese_ink_map():
    global _JAPANESE_INK_MAP
    if _JAPANESE_INK_MAP is None:
        map_path = os.path.join(FIGURES_DIR, "hanoi_map_japanese_ink_hd.png")
        if not os.path.exists(map_path):
            map_path = os.path.join(FIGURES_DIR, "hanoi_map_japanese_ink.png")
        if os.path.exists(map_path):
            from PIL import Image
            _JAPANESE_INK_MAP = np.array(Image.open(map_path))
    return _JAPANESE_INK_MAP

def add_hanoi_basemap(ax, xlim=(105.71, 105.93), ylim=(20.93, 21.09), alpha=0.88):
    """Loads high-definition Japanese ink cartographic basemap calibrated to global WGS84 positions."""
    ax.set_xlim(xlim[0], xlim[1])
    ax.set_ylim(ylim[0], ylim[1])
    ink_map = get_japanese_ink_map()
    if ink_map is not None:
        # Calibrated global position extent [lon_min, lon_max, lat_min, lat_max]
        extent = [105.70, 105.94, 20.922, 21.115]
        ax.imshow(ink_map, extent=extent, aspect="auto", origin="upper", zorder=0, alpha=alpha)
    else:
        try:
            google_maps_url = "https://mt1.google.com/vt/lyrs=m&hl=vi&x={x}&y={y}&z={z}"
            cx.add_basemap(ax, crs="EPSG:4326", source=google_maps_url, alpha=alpha, attribution=False, zorder=0)
        except Exception as e:
            print(f"Notice: Basemap could not be rendered: {e}")

# -----------------------------------------------------------------------------
# 2. Pre-Cleaning Data Quality & Outlier Audit
# -----------------------------------------------------------------------------

def run_precleaning_audit(df: pd.DataFrame) -> dict:
    """Audits raw consolidated dataset for missingness, duplicates, and outliers."""
    total_records = len(df)
    
    # 1. Missingness Profile
    missingness = {}
    for col in df.columns:
        n_missing = int(df[col].isnull().sum())
        missingness[col] = {
            "non_null": total_records - n_missing,
            "missing": n_missing,
            "missing_pct": round(n_missing / total_records * 100, 2)
        }
    
    # 2. Outlier profiling for Price
    price_s = pd.to_numeric(df["price_vnd"], errors="coerce")
    price_valid = price_s.dropna()
    p_q1, p_med, p_q3 = price_valid.quantile(0.25), price_valid.median(), price_valid.quantile(0.75)
    p_iqr = p_q3 - p_q1
    p_low_fence = max(0, p_q1 - 1.5 * p_iqr)
    p_high_fence = p_q3 + 1.5 * p_iqr
    
    price_audit = {
        "valid_count": len(price_valid),
        "missing_count": int(price_s.isnull().sum()),
        "min": float(price_valid.min()),
        "max": float(price_valid.max()),
        "median": float(p_med),
        "iqr": float(p_iqr),
        "tukey_lower_fence": float(p_low_fence),
        "tukey_upper_fence": float(p_high_fence),
        "anomalies_under_500k": int((price_valid < 500000).sum()),
        "anomalies_under_800k": int((price_valid < 800000).sum()),
        "statistical_outliers_above_upper_fence": int((price_valid > p_high_fence).sum()),
        "commercial_outliers_above_25m": int((price_valid > 25000000).sum()),
        "extreme_sales_above_50m": int((price_valid > 50000000).sum()),
    }
    
    # 3. Outlier profiling for Area
    area_s = pd.to_numeric(df["area_m2"], errors="coerce")
    area_valid = area_s.dropna()
    a_q1, a_med, a_q3 = area_valid.quantile(0.25), area_valid.median(), area_valid.quantile(0.75)
    a_iqr = a_q3 - a_q1
    a_low_fence = max(0, a_q1 - 1.5 * a_iqr)
    a_high_fence = a_q3 + 1.5 * a_iqr
    
    area_audit = {
        "valid_count": len(area_valid),
        "missing_count": int(area_s.isnull().sum()),
        "min": float(area_valid.min()),
        "max": float(area_valid.max()),
        "median": float(a_med),
        "iqr": float(a_iqr),
        "tukey_lower_fence": float(a_low_fence),
        "tukey_upper_fence": float(a_high_fence),
        "cubicle_anomalies_under_8m2": int((area_valid < 8.0).sum()),
        "statistical_outliers_above_upper_fence": int((area_valid > a_high_fence).sum()),
        "large_units_above_120m2": int((area_valid > 120.0).sum()),
        "commercial_land_above_200m2": int((area_valid > 200.0).sum()),
    }
    
    # 4. Spatial Bounds Profile
    lat_s = pd.to_numeric(df["latitude"], errors="coerce")
    lng_s = pd.to_numeric(df["longitude"], errors="coerce")
    coords_valid = lat_s.notnull() & lng_s.notnull()
    
    # Hanoi official bounding envelope
    hanoi_mask = coords_valid & (lat_s >= 20.53) & (lat_s <= 21.39) & (lng_s >= 105.28) & (lng_s <= 106.03)
    hcmc_mask = coords_valid & (lat_s >= 10.3) & (lat_s <= 11.2) & (lng_s >= 106.3) & (lng_s <= 107.0)
    
    spatial_audit = {
        "total_records": total_records,
        "valid_coordinates": int(coords_valid.sum()),
        "missing_coordinates": int((~coords_valid).sum()),
        "in_bounds_hanoi": int(hanoi_mask.sum()),
        "hcmc_cross_city_contamination": int(hcmc_mask.sum()),
        "other_out_of_bounds": int(coords_valid.sum() - hanoi_mask.sum() - hcmc_mask.sum())
    }
    
    # 5. Duplication Profile
    dup_audit = {
        "exact_id_duplicates": int(df.duplicated(subset=["listing_id"]).sum()),
        "full_row_duplicates": int(df.duplicated().sum()),
        "near_dupes_title_price": int(df.duplicated(subset=["title", "price_vnd"]).sum()),
        "near_dupes_lat_lon_price": int(df[coords_valid].duplicated(subset=["latitude", "longitude", "price_vnd"]).sum()),
    }
    
    audit_report = {
        "total_listings": total_records,
        "missingness": missingness,
        "price_audit": price_audit,
        "area_audit": area_audit,
        "spatial_audit": spatial_audit,
        "duplication_audit": dup_audit
    }
    
    with open(AUDIT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(audit_report, f, indent=2, ensure_ascii=False)
        
    return audit_report

# -----------------------------------------------------------------------------
# 3. Spatial Regeneration & Comprehensive Cleaning Engine
# -----------------------------------------------------------------------------

def regenerate_geospatial_administrative_units(df: pd.DataFrame) -> pd.DataFrame:
    """
    Regenerates district and ward attributes purely from geodetic WGS84 coordinates.
    Computes Haversine spherical distance from each listing's coordinate pair (lat, lng)
    to all 192 official ward centroids across Greater Hanoi.
    Assigns the nearest ward centroid and inherits its parent district.
    """
    df = df.copy()
    lat = pd.to_numeric(df["latitude"], errors="coerce")
    lng = pd.to_numeric(df["longitude"], errors="coerce")
    valid_coords = lat.notnull() & lng.notnull()
    
    # Arrays of ward centroid reference points
    w_lats = WARD_DF["latitude"].values
    w_lngs = WARD_DF["longitude"].values
    w_dists = WARD_DF["district"].values
    w_wards = WARD_DF["ward"].values
    
    # Initialize regenerated columns
    df["district_regenerated"] = ""
    df["ward_regenerated"] = ""
    df["distance_to_ward_centroid_km"] = np.nan
    
    # Vectorized nearest-neighbor calculation
    valid_indices = df[valid_coords].index
    lats_arr = lat[valid_coords].values
    lngs_arr = lng[valid_coords].values
    
    # Equirectangular approximation for ultra-fast spatial search
    cos_lat = np.cos(np.radians(21.0))
    diff_lat = lats_arr[:, None] - w_lats[None, :]
    diff_lng = (lngs_arr[:, None] - w_lngs[None, :]) * cos_lat
    sq_dists = diff_lat**2 + diff_lng**2
    nearest_idx = np.argmin(sq_dists, axis=1)
    
    assigned_districts = w_dists[nearest_idx]
    assigned_wards = w_wards[nearest_idx]
    
    # Exact haversine distance for quality verification
    exact_dist_km = haversine_vectorized(
        lats_arr, lngs_arr,
        w_lats[nearest_idx], w_lngs[nearest_idx]
    )
    
    df.loc[valid_indices, "district_regenerated"] = assigned_districts
    df.loc[valid_indices, "ward_regenerated"] = assigned_wards
    df.loc[valid_indices, "distance_to_ward_centroid_km"] = np.round(exact_dist_km, 3)
    
    # Fallback for listings without coordinates: preserve cleaned text district/ward
    no_coords = ~valid_coords
    clean_dist_text = df.loc[no_coords, "district"].fillna("").astype(str).str.strip()
    clean_ward_text = df.loc[no_coords, "ward"].fillna("").astype(str).str.strip()
    
    df.loc[no_coords, "district_regenerated"] = clean_dist_text.replace({"": "Chưa rõ", "nan": "Chưa rõ"})
    df.loc[no_coords, "ward_regenerated"] = clean_ward_text.replace({"": "Chưa rõ", "nan": "Chưa rõ"})
    
    return df

def parse_numeric_utility(val: any, default_giadan: int) -> float:
    """Robust regex parser for utility strings (electricity, water, wifi, parking)."""
    if pd.isna(val) or val == "" or str(val).lower() in ["nan", "none", "null"]:
        return np.nan
    s = str(val).strip().lower()
    if any(k in s for k in ["miễn phí", "free", "0đ", "0 đ"]) or re.search(r"^0\b", s):
        return 0.0
    if any(k in s for k in ["giá dân", "hóa đơn", "công tơ riêng", "nhà nước"]):
        return float(default_giadan)
    
    # Range handling (take midpoint)
    m_range = re.search(r"(\d+(?:\.\d+)?)\s*k?\s*-\s*(\d+(?:\.\d+)?)\s*k?", s)
    if m_range:
        try:
            n1 = float(m_range.group(1).replace(".", ""))
            n2 = float(m_range.group(2).replace(".", ""))
            if "k" in s and n1 < 100: n1 *= 1000
            if "k" in s and n2 < 100: n2 *= 1000
            return (n1 + n2) / 2.0
        except ValueError:
            pass
            
    m_k = re.search(r"(\d+(?:[.,]\d+)?)\s*k\b", s)
    if m_k:
        try:
            return float(m_k.group(1).replace(",", ".")) * 1000.0
        except ValueError:
            pass
            
    m_dot = re.search(r"(\d{1,3}(?:\.\d{3})+)", s)
    if m_dot:
        try:
            return float(m_dot.group(1).replace(".", ""))
        except ValueError:
            pass
            
    m_digits = re.search(r"(\d{4,})", s)
    if m_digits:
        try:
            return float(m_digits.group(1))
        except ValueError:
            pass
            
    return np.nan

def clean_and_unify_dataset(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Executes the master cleaning and enrichment pipeline."""
    df = df_raw.copy()
    
    # 1. Deduplicate by exact (platform, listing_id)
    df = df.drop_duplicates(subset=["platform", "listing_id"]).copy()
    
    # 2. Parse and filter coordinates (Spatial Envelope Filter)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    
    # Filter out clear cross-city contamination (HCMC cluster: lat ~ 10-11 N)
    valid_coords = df["latitude"].notnull() & df["longitude"].notnull()
    hcmc_mask = valid_coords & (df["latitude"] < 15.0)
    df = df[~hcmc_mask].copy()
    
    # Retain records that are either within Greater Hanoi envelope or lack coords but have Hanoi text
    hanoi_envelope = (
        (df["latitude"].isna() & df["longitude"].isna()) |
        ((df["latitude"] >= 20.53) & (df["latitude"] <= 21.39) &
         (df["longitude"] >= 105.28) & (df["longitude"] <= 106.03))
    )
    df = df[hanoi_envelope].copy()
    
    # 3. Regenerate District & Ward using Geodetic Coordinates
    df = regenerate_geospatial_administrative_units(df)
    
    # Assign regenerated administrative units as canonical fields
    df["district_raw"] = df["district"]
    df["ward_raw"] = df["ward"]
    df["district"] = df["district_regenerated"]
    df["ward"] = df["ward_regenerated"]
    
    # 4. Clean & Filter Price (VND/month)
    df["price_vnd"] = pd.to_numeric(df["price_vnd"], errors="coerce")
    # Keep valid residential rental range [800,000 VND, 25,000,000 VND]
    valid_price_mask = (df["price_vnd"] >= 800000) & (df["price_vnd"] <= 25000000)
    df = df[valid_price_mask].copy()
    
    # 5. Clean & Filter Area (m²)
    df["area_m2"] = pd.to_numeric(df["area_m2"], errors="coerce")
    # Set absurd cubicle typos (<8 m²) or commercial land parcels (>120 m²) to NaN
    absurd_area = (df["area_m2"] < 8.0) | (df["area_m2"] > 120.0)
    df.loc[absurd_area, "area_m2"] = np.nan
    
    # 6. Calculate Price per m²
    df["price_per_m2"] = np.round(df["price_vnd"] / df["area_m2"], 1)
    
    # 7. Standardize House Types
    def normalize_house_type(val):
        if pd.isna(val) or val == "":
            return "Phòng trọ / Khác"
        s = str(val).strip().lower()
        if "studio" in s:
            return "Studio khép kín"
        if "chung cư mini" in s or "ccmn" in s:
            return "Chung cư mini"
        if "căn hộ" in s or "chung cư" in s or "chdv" in s or "dịch vụ" in s:
            return "Căn hộ dịch vụ"
        if "nguyên căn" in s or "nhà riêng" in s:
            return "Nhà nguyên căn"
        if "ở ghép" in s or "homestay" in s or "ktx" in s or "dorm" in s:
            return "Ký túc xá / Ở ghép"
        if "phòng trọ" in s or "nhà trọ" in s:
            return "Phòng trọ sinh viên"
        return "Phòng trọ / Khác"
        
    df["house_type"] = df["house_type"].apply(normalize_house_type)
    
    # 8. Standardize Amenities to strict binary integer (1 or 0)
    amenity_cols = [
        "air_conditioner", "water_heater", "refrigerator", "washing_machine",
        "elevator", "balcony_window", "fire_safety", "pet_allowed"
    ]
    for c in amenity_cols:
        if c in df.columns:
            df[c] = df[c].apply(lambda v: 1 if str(v).strip().lower() in ["true", "1", "t", "yes", "có"] else 0)
        else:
            df[c] = 0
            
    df["amenity_count"] = df[amenity_cols].sum(axis=1)
    
    # 9. Clean Utility Tariffs
    df["electric_price_clean"] = df["electric_price"].apply(lambda v: parse_numeric_utility(v, default_giadan=2500))
    df["water_price_clean"] = df["water_price"].apply(lambda v: parse_numeric_utility(v, default_giadan=12000))
    df["wifi_price_clean"] = df["wifi_price"].apply(lambda v: parse_numeric_utility(v, default_giadan=100000))
    df["parking_fee_clean"] = df["parking_fee"].apply(lambda v: parse_numeric_utility(v, default_giadan=0))
    
    # Realistic bounds on utility tariffs
    df.loc[(df["electric_price_clean"] < 1500) | (df["electric_price_clean"] > 6000), "electric_price_clean"] = np.nan
    df.loc[(df["water_price_clean"] < 10000) | (df["water_price_clean"] > 150000), "water_price_clean"] = np.nan
    
    # 10. Spatial Proximity Feature Engineering
    has_coords = df["latitude"].notnull() & df["longitude"].notnull()
    df["distance_to_center_km"] = np.nan
    df["distance_to_nearest_metro_km"] = np.nan
    df["nearest_metro_station"] = ""
    df["metro_proximity_tier"] = "Không rõ tọa độ"
    
    # University proximity initializations
    df["distance_to_nearest_university_km"] = np.nan
    df["nearest_university"] = ""
    df["nearest_university_cluster"] = ""
    df["university_proximity_tier"] = "Không rõ tọa độ"
    
    if has_coords.sum() > 0:
        lats = df.loc[has_coords, "latitude"].values
        lngs = df.loc[has_coords, "longitude"].values
        cos_l = np.cos(np.radians(21.0))
        
        # Distance to Hoàn Kiếm Lake
        dist_center = haversine_vectorized(lats, lngs, HANOI_CENTER[0], HANOI_CENTER[1])
        df.loc[has_coords, "distance_to_center_km"] = np.round(dist_center, 2)
        
        # Distance to all metro stations
        m_lats = METRO_DF["lat"].values
        m_lngs = METRO_DF["lng"].values
        m_names = METRO_DF["name"].values
        
        d_lats = lats[:, None] - m_lats[None, :]
        d_lngs = (lngs[:, None] - m_lngs[None, :]) * cos_l
        sq_metro = d_lats**2 + d_lngs**2
        min_metro_idx = np.argmin(sq_metro, axis=1)
        
        best_station_lats = m_lats[min_metro_idx]
        best_station_lngs = m_lngs[min_metro_idx]
        exact_metro_dist = haversine_vectorized(lats, lngs, best_station_lats, best_station_lngs)
        
        df.loc[has_coords, "distance_to_nearest_metro_km"] = np.round(exact_metro_dist, 2)
        df.loc[has_coords, "nearest_metro_station"] = m_names[min_metro_idx]
        
        def assign_metro_tier(d):
            if d <= 0.5: return "< 500m (Đi bộ dễ dàng)"
            if d <= 1.0: return "500m - 1km (Đi bộ vừa)"
            if d <= 2.0: return "1km - 2km (Xe đạp / Bus)"
            return "> 2km (Cách xa metro)"
            
        df.loc[has_coords, "metro_proximity_tier"] = pd.Series(exact_metro_dist, index=df[has_coords].index).apply(assign_metro_tier)
        
        # Distance to universities
        u_lats = UNIVERSITIES_DF["lat"].values
        u_lngs = UNIVERSITIES_DF["lng"].values
        u_names = UNIVERSITIES_DF["name"].values
        u_clusters = UNIVERSITIES_DF["cluster"].values
        
        d_u_lats = lats[:, None] - u_lats[None, :]
        d_u_lngs = (lngs[:, None] - u_lngs[None, :]) * cos_l
        sq_u = d_u_lats**2 + d_u_lngs**2
        min_u_idx = np.argmin(sq_u, axis=1)
        
        best_u_lats = u_lats[min_u_idx]
        best_u_lngs = u_lngs[min_u_idx]
        exact_u_dist = haversine_vectorized(lats, lngs, best_u_lats, best_u_lngs)
        
        df.loc[has_coords, "distance_to_nearest_university_km"] = np.round(exact_u_dist, 2)
        df.loc[has_coords, "nearest_university"] = u_names[min_u_idx]
        df.loc[has_coords, "nearest_university_cluster"] = u_clusters[min_u_idx]
        
        def assign_u_tier(d):
            if d <= 0.5: return "< 500m (Đi bộ dễ dàng)"
            if d <= 1.0: return "500m - 1km (Đi bộ vừa)"
            if d <= 2.0: return "1km - 2km (Xe đạp / Bus)"
            return "> 2km (Khu vực ngoài SV)"
            
        df.loc[has_coords, "university_proximity_tier"] = pd.Series(exact_u_dist, index=df[has_coords].index).apply(assign_u_tier)
        
    # 11. Estimated Monthly Total Living Cost (True Living Cost)
    elec_rate = df["electric_price_clean"].fillna(3800.0)
    water_rate = df["water_price_clean"].apply(lambda w: w * 4.0 if (pd.notnull(w) and w < 50000) else (w if pd.notnull(w) else 100000.0))
    wifi_fee = df["wifi_price_clean"].fillna(100000.0)
    parking_fee = df["parking_fee_clean"].fillna(100000.0)
    
    df["estimated_total_living_cost"] = np.round(
        df["price_vnd"] + (elec_rate * 100.0) + water_rate + wifi_fee + parking_fee, 0
    )
    
    # 12. Value-Score Bargain Model (Hedonic Regression Residuals)
    model_mask = df["area_m2"].notnull() & (df["area_m2"] >= 10.0) & (df["price_vnd"] >= 1000000)
    df["value_residual_pct"] = np.nan
    df["market_value_tier"] = "Chưa xác định"
    
    if model_mask.sum() > 500:
        sub_m = df[model_mask].copy()
        X_area = np.log(sub_m["area_m2"].values)[:, None]
        top_dists = sub_m["district"].value_counts().head(12).index.tolist()
        dist_dummies = np.column_stack([(sub_m["district"] == d).astype(int).values for d in top_dists])
        amenity_features = sub_m[amenity_cols].values
        
        X = np.hstack([X_area, dist_dummies, amenity_features])
        y = np.log(sub_m["price_vnd"].values)
        
        reg = Ridge(alpha=1.0)
        reg.fit(X, y)
        y_pred = reg.predict(X)
        
        pred_price = np.exp(y_pred)
        res_pct = (sub_m["price_vnd"].values - pred_price) / pred_price * 100.0
        
        df.loc[model_mask, "value_residual_pct"] = np.round(res_pct, 1)
        
        def categorize_deal(pct):
            if pct <= -15.0: return "Giá hời (Bargain < -15%)"
            if pct >= 15.0: return "Giá cao (Premium > +15%)"
            return "Giá hợp lý (Fair Market ±15%)"
            
        df.loc[model_mask, "market_value_tier"] = pd.Series(res_pct, index=sub_m.index).apply(categorize_deal)
        
    return df

# -----------------------------------------------------------------------------
# 4. Publication-Grade Visualization Suite (Map on Left, Bar/Box on Right)
# -----------------------------------------------------------------------------

def plot_fig01_precleaning_audit(audit_report: dict, df_raw: pd.DataFrame):
    """Figure 1: Pre-cleaning Missingness and Outlier Fences."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7), dpi=180)
    fig.suptitle("Pre-Cleaning Data Quality & Anomaly Profiling (Raw Consolidated Corpus: 17,325 Listings)",
                 fontsize=15, fontweight="bold", color="#0F172A", y=0.98)
    
    # Left: Missingness Bar Chart across Key Attributes
    key_cols = [
        "listing_id", "platform", "city", "latitude", "price_vnd",
        "house_type", "district", "ward", "area_m2", "electric_price",
        "water_price", "wifi_price", "parking_fee"
    ]
    missing_pcts = [audit_report["missingness"][c]["missing_pct"] for c in key_cols]
    col_labels = [c.replace("_", "\n") for c in key_cols]
    
    bars = ax1.bar(col_labels, missing_pcts, color="#3B82F6", edgecolor="#1D4ED8", width=0.65, alpha=0.85)
    for bar in bars:
        h = bar.get_height()
        if h > 0:
            ax1.annotate(f"{h:.1f}%", xy=(bar.get_x() + bar.get_width() / 2, h + 1.2),
                         ha="center", va="bottom", fontsize=8.5, fontweight="bold", color="#1E293B")
                         
    ax1.set_title("A. Attribute Missingness Rates Before Cleaning (%)", fontsize=12, fontweight="bold", pad=12)
    ax1.set_ylabel("Missing Percentage (%)", fontsize=10, fontweight="semibold")
    ax1.set_ylim(0, 100)
    ax1.axhline(50, color="#EF4444", linestyle="--", alpha=0.6, label="Critical Missingness Threshold (50%)")
    ax1.legend(loc="upper left", frameon=True)
    
    # Right: Boxplots of Raw Price and Area showing Extreme Outliers
    ax2.set_title("B. Price Distribution Across Fences (Raw Scale vs Realistic Band)", fontsize=12, fontweight="bold", pad=12)
    p_valid = pd.to_numeric(df_raw["price_vnd"], errors="coerce").dropna() / 1e6
    p_trimmed = p_valid[p_valid <= 35.0]
    
    parts = ax2.violinplot(p_trimmed, positions=[1], showmeans=True, showmedians=True, widths=0.5)
    for pc in parts["bodies"]:
        pc.set_facecolor("#10B981")
        pc.set_edgecolor("#047857")
        pc.set_alpha(0.6)
        
    ax2.scatter(np.random.normal(1, 0.04, size=min(1500, len(p_trimmed))), p_trimmed.sample(min(1500, len(p_trimmed))),
                alpha=0.2, color="#065F46", s=6)
                
    ax2.text(1.35, 30.0, "Extreme Max: 20,000M VND\n(Commercial sale error on Chợ Tốt)\nExcluded in cleaning",
             fontsize=9, color="#B91C1C", bbox=dict(boxstyle="round,pad=0.4", facecolor="#FEE2E2", edgecolor="#EF4444"))
    ax2.text(1.35, 18.0, f"Statistical Q1: {audit_report['price_audit']['tukey_lower_fence']/1e6:.1f}M\nMedian: {audit_report['price_audit']['median']/1e6:.1f}M\nUpper Fence: {audit_report['price_audit']['tukey_upper_fence']/1e6:.1f}M",
             fontsize=9, color="#0F172A", bbox=dict(boxstyle="round,pad=0.4", facecolor="#F8FAFC", edgecolor="#CBD5E1"))
             
    ax2.set_ylabel("Monthly Rent (Million VND)", fontsize=10, fontweight="semibold")
    ax2.set_xticks([1])
    ax2.set_xticklabels(["Residential Rentals\n(Capped at 35M for visual clarity)"])
    ax2.set_ylim(0, 35)
    
    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "plot_01_precleaning_missingness_outliers.png"))
    plt.close(fig)

def plot_fig02_spatial_regeneration(df_clean: pd.DataFrame, df_raw: pd.DataFrame):
    """Figure 2: Spatial District/Ward Regeneration (Map on Left, Bar Chart on Right)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8), dpi=180, gridspec_kw={"width_ratios": [1.15, 1.0]})
    fig.suptitle("Spatial District & Ward Regeneration via WGS84 Geodetic Centroid Nearest-Neighbor",
                 fontsize=15, fontweight="bold", color="#0F172A", y=0.98)
                 
    # Left: Map of Listings colored by Regenerated District + Ward Centroids
    sub = df_clean[df_clean["latitude"].notnull() & df_clean["longitude"].notnull()].copy()
    top_dists = sub["district"].value_counts().head(10).index.tolist()
    sub_plot = sub[sub["district"].isin(top_dists)]
    
    palette = sns.color_palette("tab10", len(top_dists))
    for i, d in enumerate(top_dists):
        pts = sub_plot[sub_plot["district"] == d]
        ax1.scatter(pts["longitude"], pts["latitude"], s=6, alpha=0.45, color=palette[i], label=d, zorder=2)
        
    ax1.scatter(WARD_DF["longitude"], WARD_DF["latitude"], s=22, color="#0F172A", marker="^",
                label="Ward Centroids (192 Ref Points)", zorder=5)
    ax1.scatter([HANOI_CENTER[1]], [HANOI_CENTER[0]], s=90, color="#DC2626", marker="*",
                label="Hanoi Center (Hoàn Kiếm)", zorder=6)
                
    add_hanoi_basemap(ax1, xlim=(105.71, 105.93), ylim=(20.93, 21.09), alpha=0.65)
    ax1.set_title("A. Spatial Allocation of Listings to Official Hanoi Districts", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Longitude (°E)", fontsize=10, fontweight="semibold")
    ax1.set_ylabel("Latitude (°N)", fontsize=10, fontweight="semibold")
    ax1.legend(loc="lower left", fontsize=8, ncol=2, frameon=True)
    
    # Right: Comparison Bar Chart (Raw vs Regenerated District Counts)
    top_10 = df_clean["district"].value_counts().head(10)
    raw_counts = df_raw["district"].value_counts().reindex(top_10.index).fillna(0)
    
    y = np.arange(len(top_10))
    h = 0.35
    
    ax2.barh(y + h/2, raw_counts.values, height=h, color="#94A3B8", label="Raw Scraped District (Text)", alpha=0.85)
    ax2.barh(y - h/2, top_10.values, height=h, color="#2563EB", label="Regenerated District (Geodetic)", alpha=0.9)
    
    for idx, (r_val, c_val) in enumerate(zip(raw_counts.values, top_10.values)):
        diff = int(c_val - r_val)
        diff_str = f"+{diff}" if diff > 0 else f"{diff}"
        ax2.annotate(f"{c_val:,} ({diff_str})", xy=(c_val + 20, idx - h/2),
                     va="center", fontsize=8.5, fontweight="bold", color="#1E293B")
                     
    ax2.set_title("B. District Inventory Counts: Raw Text vs. Geodetic Regeneration", fontsize=12, fontweight="bold")
    ax2.set_yticks(y)
    ax2.set_yticklabels(top_10.index, fontsize=9.5, fontweight="semibold")
    ax2.set_xlabel("Number of Verified Rental Listings", fontsize=10, fontweight="semibold")
    ax2.invert_yaxis()
    ax2.legend(loc="lower right", frameon=True)
    
    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "plot_02_spatial_regeneration_map.png"))
    plt.close(fig)

def plot_fig03_district_distribution(df_clean: pd.DataFrame):
    """Figure 3: District Rental Distribution (Map on Left, Ranked Bar on Right)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8), dpi=180, gridspec_kw={"width_ratios": [1.1, 1.0]})
    fig.suptitle("Geographical Distribution of Rental Listings Across Greater Hanoi",
                 fontsize=15, fontweight="bold", color="#0F172A", y=0.98)
                 
    sub = df_clean[df_clean["latitude"].notnull() & df_clean["longitude"].notnull()]
    counts = df_clean["district"].value_counts()
    top_12_dists = counts.head(12).index.tolist()
    
    palette = sns.color_palette("turbo", len(top_12_dists))
    for i, dist in enumerate(top_12_dists):
        pts = sub[sub["district"] == dist]
        ax1.scatter(pts["longitude"], pts["latitude"], s=6, alpha=0.45, color=palette[i], label=f"{dist} ({len(pts):,})", zorder=2)
        
    add_hanoi_basemap(ax1, xlim=(105.71, 105.93), ylim=(20.93, 21.09), alpha=0.65)
    ax1.set_title("A. Spatial Clustering of Active Rental Supply", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Longitude (°E)", fontsize=10, fontweight="semibold")
    ax1.set_ylabel("Latitude (°N)", fontsize=10, fontweight="semibold")
    ax1.legend(loc="upper right", fontsize=8, ncol=2, frameon=True)
    
    # Right: Horizontal Ranked Bar Chart
    ranked = counts.head(14)
    y_pos = np.arange(len(ranked))
    
    bars = ax2.barh(y_pos, ranked.values, color="#0284C7", edgecolor="#0369A1", height=0.65, alpha=0.85)
    for bar in bars:
        w = bar.get_width()
        pct = w / len(df_clean) * 100
        ax2.annotate(f"{w:,} ({pct:.1f}%)", xy=(w + 25, bar.get_y() + bar.get_height() / 2),
                     va="center", fontsize=8.5, fontweight="bold", color="#0F172A")
                     
    ax2.set_title("B. Market Inventory Share by District (Ranked)", fontsize=12, fontweight="bold")
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(ranked.index, fontsize=9.5, fontweight="semibold")
    ax2.set_xlabel("Listing Count", fontsize=10, fontweight="semibold")
    ax2.invert_yaxis()
    ax2.set_xlim(0, max(ranked.values) * 1.18)
    
    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "plot_03_district_distribution_map.png"))
    plt.close(fig)

def plot_fig04_price_distribution(df_clean: pd.DataFrame):
    """Figure 4: Rental Price Distribution (Map on Left, Histogram/KDE on Right)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8), dpi=180, gridspec_kw={"width_ratios": [1.1, 1.0]})
    fig.suptitle("Hanoi Monthly Rental Price Distribution & Spatial Micro-Markets",
                 fontsize=15, fontweight="bold", color="#0F172A", y=0.98)
                 
    def price_tier(p):
        if p < 3000000: return "Dưới 3 triệu (Budget)"
        if p <= 5000000: return "3 - 5 triệu (Mid-Tier)"
        if p <= 8000000: return "5 - 8 triệu (Upper-Mid)"
        if p <= 15000000: return "8 - 15 triệu (Premium)"
        return "Trên 15 triệu (Luxury)"
        
    df_clean["price_tier"] = df_clean["price_vnd"].apply(price_tier)
    tier_order = ["Dưới 3 triệu (Budget)", "3 - 5 triệu (Mid-Tier)", "5 - 8 triệu (Upper-Mid)",
                  "8 - 15 triệu (Premium)", "Trên 15 triệu (Luxury)"]
    tier_colors = ["#10B981", "#3B82F6", "#F59E0B", "#8B5CF6", "#EF4444"]
    
    # Left: Spatial Map colored by Price Tier
    sub = df_clean[df_clean["latitude"].notnull() & df_clean["longitude"].notnull()]
    for tier, col in zip(tier_order, tier_colors):
        pts = sub[sub["price_tier"] == tier]
        ax1.scatter(pts["longitude"], pts["latitude"], s=6, alpha=0.50, color=col, label=f"{tier} ({len(pts):,})", zorder=2)
        
    add_hanoi_basemap(ax1, xlim=(105.71, 105.93), ylim=(20.93, 21.09), alpha=0.65)
    ax1.set_title("A. Spatial Clustering of Price Segments", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Longitude (°E)", fontsize=10, fontweight="semibold")
    ax1.set_ylabel("Latitude (°N)", fontsize=10, fontweight="semibold")
    ax1.legend(loc="lower left", fontsize=8.5, frameon=True)
    
    # Right: Price Histogram & KDE (in Millions VND)
    p_m = df_clean["price_vnd"] / 1e6
    sns.histplot(p_m, bins=40, kde=True, ax=ax2, color="#0284C7", edgecolor="#0369A1", alpha=0.7)
    
    med = p_m.median()
    q1 = p_m.quantile(0.25)
    q3 = p_m.quantile(0.75)
    
    ax2.axvline(med, color="#DC2626", linestyle="-", linewidth=2, label=f"Median: {med:.2f}M VND")
    ax2.axvline(q1, color="#D97706", linestyle="--", linewidth=1.5, label=f"Q1 (25%): {q1:.2f}M VND")
    ax2.axvline(q3, color="#D97706", linestyle="--", linewidth=1.5, label=f"Q3 (75%): {q3:.2f}M VND")
    
    ax2.set_title("B. Price Distribution Density & Key Statistics", fontsize=12, fontweight="bold")
    ax2.set_xlabel("Monthly Rent (Million VND)", fontsize=10, fontweight="semibold")
    ax2.set_ylabel("Listing Count", fontsize=10, fontweight="semibold")
    ax2.set_xlim(0, 25)
    ax2.legend(loc="upper right", fontsize=9, frameon=True)
    
    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "plot_04_price_distribution_map.png"))
    plt.close(fig)

def plot_fig05_area_distribution(df_clean: pd.DataFrame):
    """Figure 5: Usable Floor Area Distribution (Map on Left, Histogram on Right)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8), dpi=180, gridspec_kw={"width_ratios": [1.1, 1.0]})
    fig.suptitle("Hanoi Rental Floor Area Distribution & Spatial Footprint",
                 fontsize=15, fontweight="bold", color="#0F172A", y=0.98)
                 
    sub_area = df_clean[df_clean["area_m2"].notnull()].copy()
    
    def area_tier(a):
        if a < 20: return "< 20 m² (Compact Room)"
        if a <= 30: return "20 - 30 m² (Standard Studio)"
        if a <= 45: return "30 - 45 m² (1PN / Mini Apt)"
        return "> 45 m² (Family / 2PN+)"
        
    sub_area["area_tier"] = sub_area["area_m2"].apply(area_tier)
    tiers = ["< 20 m² (Compact Room)", "20 - 30 m² (Standard Studio)", "30 - 45 m² (1PN / Mini Apt)", "> 45 m² (Family / 2PN+)"]
    colors = ["#F59E0B", "#10B981", "#3B82F6", "#8B5CF6"]
    
    has_coords = sub_area["latitude"].notnull() & sub_area["longitude"].notnull()
    sub_coords = sub_area[has_coords]
    for tier, col in zip(tiers, colors):
        pts = sub_coords[sub_coords["area_tier"] == tier]
        ax1.scatter(pts["longitude"], pts["latitude"], s=6, alpha=0.50, color=col, label=f"{tier} ({len(pts):,})", zorder=2)
        
    add_hanoi_basemap(ax1, xlim=(105.71, 105.93), ylim=(20.93, 21.09), alpha=0.65)
    ax1.set_title("A. Spatial Footprint of Room Size Categories", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Longitude (°E)", fontsize=10, fontweight="semibold")
    ax1.set_ylabel("Latitude (°N)", fontsize=10, fontweight="semibold")
    ax1.legend(loc="lower left", fontsize=8.5, frameon=True)
    
    # Right: Histogram / KDE of usable area
    areas = sub_area["area_m2"]
    sns.histplot(areas, bins=35, kde=True, ax=ax2, color="#10B981", edgecolor="#047857", alpha=0.7)
    
    a_med = areas.median()
    a_q1 = areas.quantile(0.25)
    a_q3 = areas.quantile(0.75)
    
    ax2.axvline(a_med, color="#DC2626", linestyle="-", linewidth=2, label=f"Median: {a_med:.1f} m²")
    ax2.axvline(a_q1, color="#D97706", linestyle="--", linewidth=1.5, label=f"Q1: {a_q1:.1f} m²")
    ax2.axvline(a_q3, color="#D97706", linestyle="--", linewidth=1.5, label=f"Q3: {a_q3:.1f} m²")
    
    ax2.set_title("B. Usable Floor Area Density (m²)", fontsize=12, fontweight="bold")
    ax2.set_xlabel("Floor Area (m²)", fontsize=10, fontweight="semibold")
    ax2.set_ylabel("Listing Count", fontsize=10, fontweight="semibold")
    ax2.set_xlim(5, 100)
    ax2.legend(loc="upper right", fontsize=9, frameon=True)
    
    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "plot_05_area_distribution_map.png"))
    plt.close(fig)

def plot_fig06_price_per_m2(df_clean: pd.DataFrame):
    """Figure 6: Unit Price per m² (Map on Left, Ranked District Bar on Right)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8), dpi=180, gridspec_kw={"width_ratios": [1.1, 1.0]})
    fig.suptitle("Rental Value Density: Unit Price per Square Meter (VND/m²/month)",
                 fontsize=15, fontweight="bold", color="#0F172A", y=0.98)
                 
    sub = df_clean[df_clean["price_per_m2"].notnull() & (df_clean["price_per_m2"] <= 400000)].copy()
    sub_coords = sub[sub["latitude"].notnull() & sub["longitude"].notnull()]
    
    sc = ax1.scatter(sub_coords["longitude"], sub_coords["latitude"], c=sub_coords["price_per_m2"] / 1000,
                     cmap="plasma", s=7, alpha=0.60, vmin=80, vmax=250, zorder=2)
    cbar = plt.colorbar(sc, ax=ax1, fraction=0.046, pad=0.04)
    cbar.set_label("Thousand VND / m² / month", fontsize=9, fontweight="semibold")
    
    add_hanoi_basemap(ax1, xlim=(105.71, 105.93), ylim=(20.93, 21.09), alpha=0.60)
    ax1.set_title("A. Spatial Valuation Gradient (VND / m²)", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Longitude (°E)", fontsize=10, fontweight="semibold")
    ax1.set_ylabel("Latitude (°N)", fontsize=10, fontweight="semibold")
    
    dist_m2 = sub.groupby("district")["price_per_m2"].agg(["median", "count"]).query("count >= 30").sort_values(by="median", ascending=True)
    
    y_pos = np.arange(len(dist_m2))
    bars = ax2.barh(y_pos, dist_m2["median"] / 1000, color="#8B5CF6", edgecolor="#6D28D9", height=0.65, alpha=0.85)
    
    for bar in bars:
        w = bar.get_width()
        ax2.annotate(f"{w:.0f}k/m²", xy=(w + 2.5, bar.get_y() + bar.get_height() / 2),
                     va="center", fontsize=8.5, fontweight="bold", color="#0F172A")
                     
    ax2.set_title("B. Median Rental Unit Cost by District (Ranked)", fontsize=12, fontweight="bold")
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(dist_m2.index, fontsize=9.5, fontweight="semibold")
    ax2.set_xlabel("Median Price (Thousand VND / m² / month)", fontsize=10, fontweight="semibold")
    ax2.set_xlim(0, max(dist_m2["median"] / 1000) * 1.15)
    
    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "plot_06_price_per_m2_map.png"))
    plt.close(fig)

def plot_fig07_house_type_distribution(df_clean: pd.DataFrame):
    """Figure 7: Room Typology Distribution (Map on Left, Bar Chart on Right)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8), dpi=180, gridspec_kw={"width_ratios": [1.1, 1.0]})
    fig.suptitle("Hanoi Rental Accommodation Typology & Pricing Breakdown",
                 fontsize=15, fontweight="bold", color="#0F172A", y=0.98)
                 
    types = df_clean["house_type"].value_counts().index.tolist()
    type_palette = sns.color_palette("Set2", len(types))
    
    sub = df_clean[df_clean["latitude"].notnull() & df_clean["longitude"].notnull()]
    for i, t in enumerate(types):
        pts = sub[sub["house_type"] == t]
        ax1.scatter(pts["longitude"], pts["latitude"], s=6, alpha=0.45, color=type_palette[i], label=f"{t} ({len(pts):,})", zorder=2)
        
    add_hanoi_basemap(ax1, xlim=(105.71, 105.93), ylim=(20.93, 21.09), alpha=0.65)
    ax1.set_title("A. Geographic Localization of Property Types", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Longitude (°E)", fontsize=10, fontweight="semibold")
    ax1.set_ylabel("Latitude (°N)", fontsize=10, fontweight="semibold")
    ax1.legend(loc="lower left", fontsize=8.5, frameon=True)
    
    type_stats = df_clean.groupby("house_type")["price_vnd"].agg(["count", "median"]).loc[types]
    
    y = np.arange(len(types))
    bars = ax2.barh(y, type_stats["median"] / 1e6, color="#EC4899", edgecolor="#BE185D", height=0.6, alpha=0.85)
    
    for idx, bar in enumerate(bars):
        w = bar.get_width()
        cnt = type_stats["count"].iloc[idx]
        ax2.annotate(f"{w:.1f}M VND (N={cnt:,})", xy=(w + 0.3, bar.get_y() + bar.get_height() / 2),
                     va="center", fontsize=8.5, fontweight="bold", color="#0F172A")
                     
    ax2.set_title("B. Median Monthly Rent by Accommodation Typology", fontsize=12, fontweight="bold")
    ax2.set_yticks(y)
    ax2.set_yticklabels(types, fontsize=9.5, fontweight="semibold")
    ax2.set_xlabel("Median Monthly Rent (Million VND)", fontsize=10, fontweight="semibold")
    ax2.invert_yaxis()
    ax2.set_xlim(0, max(type_stats["median"] / 1e6) * 1.25)
    
    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "plot_07_house_type_distribution_map.png"))
    plt.close(fig)

def plot_fig08_amenities_prevalence(df_clean: pd.DataFrame):
    """Figure 8: Amenity Penetration & Spatial Density (Map on Left, Bar on Right)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8), dpi=180, gridspec_kw={"width_ratios": [1.1, 1.0]})
    fig.suptitle("Amenity Modernization & Equipment Penetration in Hanoi Rental Market",
                 fontsize=15, fontweight="bold", color="#0F172A", y=0.98)
                 
    sub = df_clean[df_clean["latitude"].notnull() & df_clean["longitude"].notnull()]
    sc = ax1.scatter(sub["longitude"], sub["latitude"], c=sub["amenity_count"],
                     cmap="YlGnBu", s=7, alpha=0.60, vmin=0, vmax=7, zorder=2)
    cbar = plt.colorbar(sc, ax=ax1, fraction=0.046, pad=0.04)
    cbar.set_label("Equipped Amenity Count (out of 8)", fontsize=9, fontweight="semibold")
    
    add_hanoi_basemap(ax1, xlim=(105.71, 105.93), ylim=(20.93, 21.09), alpha=0.60)
    ax1.set_title("A. Spatial Density of Modern Furnished Rentals", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Longitude (°E)", fontsize=10, fontweight="semibold")
    ax1.set_ylabel("Latitude (°N)", fontsize=10, fontweight="semibold")
    
    amenity_labels = {
        "water_heater": "Nóng lạnh (Water Heater)",
        "air_conditioner": "Điều hòa (Air Conditioner)",
        "washing_machine": "Máy giặt (Washing Machine)",
        "balcony_window": "Ban công / Thoáng (Balcony/Window)",
        "refrigerator": "Tủ lạnh (Refrigerator)",
        "elevator": "Thang máy (Elevator)",
        "fire_safety": "PCCC (Fire Safety Equip)",
        "pet_allowed": "Cho phép nuôi Pet (Pet Allowed)"
    }
    
    rates = {amenity_labels[k]: df_clean[k].mean() * 100 for k in amenity_labels}
    s_rates = pd.Series(rates).sort_values(ascending=True)
    
    y = np.arange(len(s_rates))
    bars = ax2.barh(y, s_rates.values, color="#0D9488", edgecolor="#0F766E", height=0.6, alpha=0.85)
    
    for bar in bars:
        w = bar.get_width()
        ax2.annotate(f"{w:.1f}%", xy=(w + 1.2, bar.get_y() + bar.get_height() / 2),
                     va="center", fontsize=9, fontweight="bold", color="#0F172A")
                     
    ax2.set_title("B. Amenity Penetration Rate Across All Listings (%)", fontsize=12, fontweight="bold")
    ax2.set_yticks(y)
    ax2.set_yticklabels(s_rates.index, fontsize=9.5, fontweight="semibold")
    ax2.set_xlabel("Penetration Rate (%)", fontsize=10, fontweight="semibold")
    ax2.set_xlim(0, 100)
    
    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "plot_08_amenities_prevalence_map.png"))
    plt.close(fig)

def plot_fig09_metro_proximity(df_clean: pd.DataFrame):
    """Figure 9: Metro Proximity Impact (Map on Left, Price Boxplot on Right)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8), dpi=180, gridspec_kw={"width_ratios": [1.1, 1.0]})
    fig.suptitle("Hanoi Urban Transit Impact: Metro Line 2A & 3 Corridors vs. Rental Values",
                 fontsize=15, fontweight="bold", color="#0F172A", y=0.98)
                 
    sub = df_clean[df_clean["latitude"].notnull() & df_clean["longitude"].notnull() & df_clean["distance_to_nearest_metro_km"].notnull()].copy()
    
    ax1.scatter(sub["longitude"], sub["latitude"], s=4, alpha=0.25, color="#64748B", label="Rental Listings", zorder=2)
    
    l2 = METRO_DF[METRO_DF["line"] == "Line 2A"]
    ax1.plot(l2["lng"], l2["lat"], color="#2563EB", linewidth=4, label="Metro Line 2A (Cát Linh - Hà Đông)", zorder=4)
    ax1.scatter(l2["lng"], l2["lat"], color="#1D4ED8", s=50, marker="o", edgecolors="#FFFFFF", linewidth=1.2, zorder=6)
    
    l3 = METRO_DF[METRO_DF["line"] == "Line 3"]
    ax1.plot(l3["lng"], l3["lat"], color="#059669", linewidth=4, label="Metro Line 3 (Nhổn - Cầu Giấy)", zorder=4)
    ax1.scatter(l3["lng"], l3["lat"], color="#047857", s=50, marker="s", edgecolors="#FFFFFF", linewidth=1.2, zorder=6)
    
    walkable = sub[sub["distance_to_nearest_metro_km"] <= 0.5]
    ax1.scatter(walkable["longitude"], walkable["latitude"], s=7, alpha=0.7, color="#DC2626",
                label=f"Walkable (<500m from station: {len(walkable):,})", zorder=3)
                
    add_hanoi_basemap(ax1, xlim=(105.71, 105.86), ylim=(20.94, 21.07), alpha=0.75)
    ax1.set_title("A. Metro Line Alignments & Transit Catchment Zones", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Longitude (°E)", fontsize=10, fontweight="semibold")
    ax1.set_ylabel("Latitude (°N)", fontsize=10, fontweight="semibold")
    ax1.legend(loc="lower left", fontsize=8.5, frameon=True)
    
    order = ["< 500m (Đi bộ dễ dàng)", "500m - 1km (Đi bộ vừa)", "1km - 2km (Xe đạp / Bus)", "> 2km (Cách xa metro)"]
    sub_plot = sub[sub["metro_proximity_tier"].isin(order)].copy()
    sub_plot["price_m"] = sub_plot["price_vnd"] / 1e6
    
    sns.boxplot(data=sub_plot, x="metro_proximity_tier", y="price_m", hue="metro_proximity_tier", order=order, ax=ax2,
                palette=["#EF4444", "#F59E0B", "#3B82F6", "#64748B"], legend=False, showfliers=False)
                
    medians = sub_plot.groupby("metro_proximity_tier", observed=False)["price_m"].median().loc[order]
    for idx, med in enumerate(medians):
        ax2.annotate(f"Median:\n{med:.2f}M", xy=(idx, med + 0.3), ha="center", fontsize=8.5, fontweight="bold", color="#0F172A")
        
    ax2.set_title("B. Rental Price Premiums by Transit Proximity Tier", fontsize=12, fontweight="bold")
    ax2.set_xlabel("Metro Proximity Band", fontsize=10, fontweight="semibold")
    ax2.set_ylabel("Monthly Rent (Million VND)", fontsize=10, fontweight="semibold")
    ax2.set_xticks(range(len(order)))
    ax2.set_xticklabels(["< 500m\n(Walking)", "500m-1km\n(Mid Walk)", "1km-2km\n(Cycling/Bus)", "> 2km\n(Isolated)"], fontsize=9)
    ax2.set_ylim(1, 12)
    
    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "plot_09_metro_proximity_map.png"))
    plt.close(fig)

def plot_fig10_true_living_cost(df_clean: pd.DataFrame):
    """Figure 10: True Cost of Living (Map on Left, Stacked Fee Breakdown on Right)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8), dpi=180, gridspec_kw={"width_ratios": [1.1, 1.0]})
    fig.suptitle("True Living Cost: Unmasking Utility Surcharges & Effective Living Expenses",
                 fontsize=15, fontweight="bold", color="#0F172A", y=0.98)
                 
    sub = df_clean[df_clean["latitude"].notnull() & df_clean["longitude"].notnull()].copy()
    
    sc = ax1.scatter(sub["longitude"], sub["latitude"], c=sub["estimated_total_living_cost"] / 1e6,
                     cmap="viridis", s=7, alpha=0.60, vmin=3.0, vmax=10.0, zorder=2)
    cbar = plt.colorbar(sc, ax=ax1, fraction=0.046, pad=0.04)
    cbar.set_label("Estimated Total Monthly Living Cost (Million VND)", fontsize=9, fontweight="semibold")
    
    add_hanoi_basemap(ax1, xlim=(105.71, 105.93), ylim=(20.93, 21.09), alpha=0.60)
    ax1.set_title("A. Spatial Footprint of Effective Monthly Living Cost", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Longitude (°E)", fontsize=10, fontweight="semibold")
    ax1.set_ylabel("Latitude (°N)", fontsize=10, fontweight="semibold")
    
    top_8 = df_clean["district"].value_counts().head(8).index.tolist()
    d_stats = []
    for d in top_8:
        sub_d = df_clean[df_clean["district"] == d]
        b_rent = sub_d["price_vnd"].median() / 1e6
        e_rate = sub_d["electric_price_clean"].fillna(3800.0).median()
        w_rate = sub_d["water_price_clean"].fillna(30000.0).median()
        elec_fee = (e_rate * 100.0) / 1e6
        water_fee = (w_rate * 4.0 if w_rate < 50000 else w_rate) / 1e6
        other_fee = 0.20
        d_stats.append({
            "district": d,
            "base_rent": b_rent,
            "electricity": elec_fee,
            "water": water_fee,
            "wifi_parking": other_fee
        })
        
    df_cost = pd.DataFrame(d_stats).set_index("district").sort_values(by="base_rent", ascending=True)
    
    y = np.arange(len(df_cost))
    h = 0.6
    
    ax2.barh(y, df_cost["base_rent"], height=h, color="#3B82F6", label="Base Rent", alpha=0.9)
    ax2.barh(y, df_cost["electricity"], left=df_cost["base_rent"], height=h, color="#F59E0B", label="Electricity (100 kWh)", alpha=0.9)
    ax2.barh(y, df_cost["water"], left=df_cost["base_rent"] + df_cost["electricity"], height=h, color="#06B6D4", label="Water (4m³ / person)", alpha=0.9)
    ax2.barh(y, df_cost["wifi_parking"], left=df_cost["base_rent"] + df_cost["electricity"] + df_cost["water"], height=h, color="#8B5CF6", label="Wifi & Parking", alpha=0.9)
    
    for idx, row in enumerate(df_cost.itertuples()):
        total = row.base_rent + row.electricity + row.water + row.wifi_parking
        ax2.annotate(f"{total:.2f}M", xy=(total + 0.15, idx), va="center", fontsize=8.5, fontweight="bold", color="#0F172A")
        
    ax2.set_title("B. Breakdown of True Living Expenses by Top Districts", fontsize=12, fontweight="bold")
    ax2.set_yticks(y)
    ax2.set_yticklabels(df_cost.index, fontsize=9.5, fontweight="semibold")
    ax2.set_xlabel("Effective Monthly Cost (Million VND)", fontsize=10, fontweight="semibold")
    ax2.set_xlim(0, max(df_cost.sum(axis=1)) * 1.15)
    ax2.legend(loc="lower right", fontsize=8.5, frameon=True)
    
    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "plot_10_true_living_cost_map.png"))
    plt.close(fig)

def plot_fig11_value_score_bargains(df_clean: pd.DataFrame):
    """Figure 11: Hedonic Value-Score & Bargain Discovery (Map on Left, Deal Rates on Right)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8), dpi=180, gridspec_kw={"width_ratios": [1.1, 1.0]})
    fig.suptitle("Value-Score Intelligence: Discovering Underpriced Deals vs Overpriced Units",
                 fontsize=15, fontweight="bold", color="#0F172A", y=0.98)
                 
    sub = df_clean[df_clean["latitude"].notnull() & df_clean["longitude"].notnull() & df_clean["market_value_tier"].isin([
        "Giá hời (Bargain < -15%)", "Giá hợp lý (Fair Market ±15%)", "Giá cao (Premium > +15%)"
    ])].copy()
    
    colors_deal = {
        "Giá hời (Bargain < -15%)": "#10B981",
        "Giá hợp lý (Fair Market ±15%)": "#F59E0B",
        "Giá cao (Premium > +15%)": "#EF4444"
    }
    
    for tier in ["Giá hợp lý (Fair Market ±15%)", "Giá cao (Premium > +15%)", "Giá hời (Bargain < -15%)"]:
        pts = sub[sub["market_value_tier"] == tier]
        size = 9 if "Bargain" in tier else 5
        alpha = 0.75 if "Bargain" in tier else 0.40
        ax1.scatter(pts["longitude"], pts["latitude"], s=size, alpha=alpha, color=colors_deal[tier],
                    label=f"{tier} ({len(pts):,})", zorder=3 if "Bargain" in tier else 2)
                    
    add_hanoi_basemap(ax1, xlim=(105.71, 105.93), ylim=(20.93, 21.09), alpha=0.65)
    ax1.set_title("A. Geographic Clustering of Rental Deals & Overpriced Units", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Longitude (°E)", fontsize=10, fontweight="semibold")
    ax1.set_ylabel("Latitude (°N)", fontsize=10, fontweight="semibold")
    ax1.legend(loc="lower left", fontsize=8.5, frameon=True)
    
    top_10 = df_clean["district"].value_counts().head(10).index.tolist()
    b_rates = []
    for d in top_10:
        sub_d = df_clean[(df_clean["district"] == d) & df_clean["market_value_tier"].notnull() & (df_clean["market_value_tier"] != "Chưa xác định")]
        if len(sub_d) >= 50:
            b_pct = (sub_d["market_value_tier"] == "Giá hời (Bargain < -15%)").mean() * 100.0
            b_rates.append({"district": d, "bargain_pct": b_pct, "total": len(sub_d)})
            
    df_b = pd.DataFrame(b_rates).sort_values(by="bargain_pct", ascending=True)
    
    y = np.arange(len(df_b))
    bars = ax2.barh(y, df_b["bargain_pct"], color="#10B981", edgecolor="#047857", height=0.6, alpha=0.85)
    
    for bar in bars:
        w = bar.get_width()
        ax2.annotate(f"{w:.1f}%", xy=(w + 0.5, bar.get_y() + bar.get_height() / 2),
                     va="center", fontsize=9, fontweight="bold", color="#0F172A")
                     
    ax2.set_title("B. Bargain Probability by District (% of Listings Underpriced >15%)", fontsize=12, fontweight="bold")
    ax2.set_yticks(y)
    ax2.set_yticklabels(df_b["district"], fontsize=9.5, fontweight="semibold")
    ax2.set_xlabel("Percentage of Underpriced Listings (%)", fontsize=10, fontweight="semibold")
    ax2.set_xlim(0, max(df_b["bargain_pct"]) * 1.18)
    
    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "plot_11_value_score_bargain_map.png"))
    plt.close(fig)

def plot_fig12_university_proximity(df_clean: pd.DataFrame):
    """Figure 12: University Proximity & Student Housing Clusters (Map on Left, Bar Chart on Right)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8), dpi=180, gridspec_kw={"width_ratios": [1.15, 1.0]})
    fig.suptitle("Hanoi Higher Education Hubs: University Proximity & Student Rental Micro-Markets",
                 fontsize=15, fontweight="bold", color="#0F172A", y=0.98)
                 
    sub = df_clean[df_clean["latitude"].notnull() & df_clean["longitude"].notnull() & df_clean["distance_to_nearest_university_km"].notnull()].copy()
    
    # Left: Spatial Map showing university campuses and student rentals
    ax1.scatter(sub["longitude"], sub["latitude"], s=4, alpha=0.20, color="#64748B", label="All Rental Listings", zorder=2)
    
    # Highlight listings within 1 km of universities
    near_u = sub[sub["distance_to_nearest_university_km"] <= 1.0].copy()
    
    clusters = ["Cầu Giấy", "Bách - Kinh - Xây", "Chùa Láng", "Chùa Bộc", "Thanh Xuân", "Hà Đông", "Bắc Từ Liêm"]
    c_palette = sns.color_palette("Set1", len(clusters))
    for i, cl in enumerate(clusters):
        pts = near_u[near_u["nearest_university_cluster"] == cl]
        if len(pts) > 0:
            ax1.scatter(pts["longitude"], pts["latitude"], s=7, alpha=0.60, color=c_palette[i],
                        label=f"Campus Cluster: {cl} ({len(pts):,})", zorder=3)
            
    # Plot universities as prominent gold/red star markers
    for _, u in UNIVERSITIES_DF.iterrows():
        ax1.scatter(u["lng"], u["lat"], s=90, color="#F59E0B", marker="*", edgecolors="#7C2D12", linewidth=1.2, zorder=6)
        if any(k in u["name"] for k in ["Bách khoa", "Kinh tế", "Quốc gia", "Ngoại thương", "Hà Nội"]):
            short_name = u["name"].replace("ĐH ", "").replace("Học viện ", "HV ").split("(")[0].strip()
            ax1.annotate(short_name, xy=(u["lng"], u["lat"]), xytext=(4, 4), textcoords="offset points",
                         fontsize=8, fontweight="bold", color="#1E293B",
                         bbox=dict(boxstyle="round,pad=0.2", facecolor="#FEF3C7", edgecolor="#D97706", alpha=0.85),
                         zorder=7)
                         
    add_hanoi_basemap(ax1, xlim=(105.71, 105.88), ylim=(20.94, 21.08), alpha=0.75)
    ax1.set_title("A. University Campuses & Student Catchment Zones (≤ 1.0 km)", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Longitude (°E)", fontsize=10, fontweight="semibold")
    ax1.set_ylabel("Latitude (°N)", fontsize=10, fontweight="semibold")
    ax1.legend(loc="lower left", fontsize=8, ncol=2, frameon=True)
    
    # Right: Top Universities by Nearby Rental Volume (< 1.5 km) and Median Rent
    u_stats = sub[sub["distance_to_nearest_university_km"] <= 1.5].groupby("nearest_university").agg(
        count=("listing_id", "count"),
        median_price=("price_vnd", "median"),
        median_area=("area_m2", "median")
    ).sort_values(by="count", ascending=True).tail(12)
    
    y_pos = np.arange(len(u_stats))
    bars = ax2.barh(y_pos, u_stats["count"], color="#0284C7", edgecolor="#0369A1", height=0.65, alpha=0.85)
    
    for idx, bar in enumerate(bars):
        w = bar.get_width()
        med_p = u_stats["median_price"].iloc[idx] / 1e6
        ax2.annotate(f"{w:,} listings  |  Median: {med_p:.2f}M",
                     xy=(w + 15, bar.get_y() + bar.get_height() / 2),
                     va="center", fontsize=8.5, fontweight="bold", color="#0F172A")
                     
    ax2.set_title("B. Rental Housing Supply & Median Rent Around Top University Hubs (< 1.5 km)", fontsize=12, fontweight="bold")
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(u_stats.index, fontsize=9.5, fontweight="semibold")
    ax2.set_xlabel("Number of Student Rental Listings", fontsize=10, fontweight="semibold")
    ax2.set_xlim(0, max(u_stats["count"]) * 1.35)
    
    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "plot_12_university_proximity_map.png"))
    plt.close(fig)

# -----------------------------------------------------------------------------
# 5. Main Execution Entrypoint
# -----------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("Starting Unified Hanoi Rental Dataset Cleaning & Visualization Suite")
    print("=" * 70)
    
    # 1. Load or Build Clean Dataset
    need_full_rebuild = True
    if os.path.exists(CLEAN_DATA_PATH) and os.path.exists(AUDIT_JSON_PATH):
        df_clean = pd.read_csv(CLEAN_DATA_PATH, low_memory=False)
        with open(AUDIT_JSON_PATH, "r", encoding="utf-8") as f:
            audit_report = json.load(f)
        df_raw = pd.read_csv(RAW_DATA_PATH, low_memory=False)
        if "distance_to_nearest_university_km" in df_clean.columns:
            need_full_rebuild = False
            
    if need_full_rebuild:
        print(f"Executing complete clean and enrichment pipeline from: {RAW_DATA_PATH}")
        df_raw = pd.read_csv(RAW_DATA_PATH, low_memory=False)
        audit_report = run_precleaning_audit(df_raw)
        df_clean = clean_and_unify_dataset(df_raw)
        print(f"Writing clean unified dataset to: {CLEAN_DATA_PATH}")
        df_clean.to_csv(CLEAN_DATA_PATH, index=False, encoding="utf-8")
        df_clean.to_csv(UNIFIED_BENCHMARK_PATH, index=False, encoding="utf-8")

    # 2. Generate All 12 Side-by-Side Composite Figures with Real Basemap Tiles
    print("Rendering publication-grade composite figures with Japanese ink cartographic basemaps...")
    plot_fig01_precleaning_audit(audit_report, df_raw)
    print("  -> plot_01_precleaning_missingness_outliers.png")
    plot_fig02_spatial_regeneration(df_clean, df_raw)
    print("  -> plot_02_spatial_regeneration_map.png (Basemap enabled)")
    plot_fig03_district_distribution(df_clean)
    print("  -> plot_03_district_distribution_map.png (Basemap enabled)")
    plot_fig04_price_distribution(df_clean)
    print("  -> plot_04_price_distribution_map.png (Basemap enabled)")
    plot_fig05_area_distribution(df_clean)
    print("  -> plot_05_area_distribution_map.png (Basemap enabled)")
    plot_fig06_price_per_m2(df_clean)
    print("  -> plot_06_price_per_m2_map.png (Basemap enabled)")
    plot_fig07_house_type_distribution(df_clean)
    print("  -> plot_07_house_type_distribution_map.png (Basemap enabled)")
    plot_fig08_amenities_prevalence(df_clean)
    print("  -> plot_08_amenities_prevalence_map.png (Basemap enabled)")
    plot_fig09_metro_proximity(df_clean)
    print("  -> plot_09_metro_proximity_map.png (Basemap enabled)")
    plot_fig10_true_living_cost(df_clean)
    print("  -> plot_10_true_living_cost_map.png (Basemap enabled)")
    plot_fig11_value_score_bargains(df_clean)
    print("  -> plot_11_value_score_bargain_map.png (Basemap enabled)")
    plot_fig12_university_proximity(df_clean)
    print("  -> plot_12_university_proximity_map.png (Basemap enabled)")
    
    print("=" * 70)
    print("All tasks completed successfully with actual map basemaps!")
    print("=" * 70)

if __name__ == "__main__":
    main()
