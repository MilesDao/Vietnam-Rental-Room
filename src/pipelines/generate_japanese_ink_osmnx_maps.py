#!/usr/bin/env python3
"""
OSMnx Vector Japanese Ink Map Rendering Suite for Hanoi Rental Market
====================================================================
Follows Carlos Cilleruelo (Towards Data Science) cartographic methodology:
- True native GPS positioning without artificial stretch or distortion.
- OpenStreetMap vector roads and water networks in Tokyo Japanese Ink palette.
- Filters out all listings located on water bodies (West Lake, Red River, lakes).
- 50% enlarged floating cartographic legends for high legibility.
- District price comparison segmented by official GADM district borders with
  a smooth Pink (lower price) to Red (higher price) continuous gradient.
"""

import os
import math
import numpy as np
import pandas as pd
import geopandas as gpd
import osmnx as ox
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap, Normalize
from shapely.geometry import box, Point
from pyproj import Transformer

# Resource caps
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"
os.environ["OPENBLAS_NUM_THREADS"] = "4"

BASE_DIR = "/home/totallynotminh/Documents/FunDS"
DATA_PATH = os.path.join(BASE_DIR, "data/hanoi_rentals_cleaned_unified.csv")
ROADS_PATH = os.path.join(BASE_DIR, "data/hanoi_osm_roads.graphml")
WATER_PATH = os.path.join(BASE_DIR, "data/hanoi_osm_water.geojson")
DISTRICTS_PATH = os.path.join(BASE_DIR, "data/hanoi_districts.geojson")
FIGURES_DIR = os.path.join(BASE_DIR, "figures")

# Metro Stations (Lines 2A & 3)
METRO_STATIONS = [
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
    {"line": "Line 3", "name": "Nhổn", "lat": 21.0538, "lng": 105.7335},
    {"line": "Line 3", "name": "Minh Khai", "lat": 21.0503, "lng": 105.7441},
    {"line": "Line 3", "name": "Phú Diễn", "lat": 21.0475, "lng": 105.7552},
    {"line": "Line 3", "name": "Cầu Diễn", "lat": 21.0425, "lng": 105.7677},
    {"line": "Line 3", "name": "Lê Đức Thọ", "lat": 21.0381, "lng": 105.7766},
    {"line": "Line 3", "name": "Đại học Quốc gia", "lat": 21.0360, "lng": 105.7830},
    {"line": "Line 3", "name": "Chùa Hà", "lat": 21.0336, "lng": 105.7944},
    {"line": "Line 3", "name": "Cầu Giấy", "lat": 21.0298, "lng": 105.8048},
]

# Major Universities
UNIVERSITIES = [
    {"name": "ĐH Quốc gia (VNU)", "cluster": "Cầu Giấy", "lat": 21.0378, "lng": 105.7818},
    {"name": "ĐH Sư phạm (HNUE)", "cluster": "Cầu Giấy", "lat": 21.0366, "lng": 105.7839},
    {"name": "ĐH Thương mại (TMU)", "cluster": "Cầu Giấy", "lat": 21.0365, "lng": 105.7725},
    {"name": "HV Báo chí (AJC)", "cluster": "Cầu Giấy", "lat": 21.0372, "lng": 105.7925},
    {"name": "ĐH Giao thông Vận tải (UTC)", "cluster": "Cầu Giấy", "lat": 21.0289, "lng": 105.8038},
    {"name": "ĐH Ngoại thương (FTU)", "cluster": "Chùa Láng", "lat": 21.0232, "lng": 105.8055},
    {"name": "ĐH Luật Hà Nội (HLU)", "cluster": "Chùa Láng", "lat": 21.0185, "lng": 105.8115},
    {"name": "HV Ngân hàng (BA)", "cluster": "Chùa Bộc", "lat": 21.0092, "lng": 105.8290},
    {"name": "ĐH Thủy lợi (TLU)", "cluster": "Chùa Bộc", "lat": 21.0075, "lng": 105.8242},
    {"name": "ĐH Y Hà Nội (HMU)", "cluster": "Chùa Bộc", "lat": 21.0028, "lng": 105.8315},
    {"name": "ĐH Bách khoa (HUST)", "cluster": "Bách - Kinh - Xây", "lat": 21.0051, "lng": 105.8432},
    {"name": "ĐH Kinh tế Quốc dân (NEU)", "cluster": "Bách - Kinh - Xây", "lat": 20.9965, "lng": 105.8425},
    {"name": "ĐH Xây dựng (HUCE)", "cluster": "Bách - Kinh - Xây", "lat": 21.0035, "lng": 105.8428},
    {"name": "ĐH Mở Hà Nội (HOU)", "cluster": "Bách - Kinh - Xây", "lat": 21.0055, "lng": 105.8475},
    {"name": "ĐH Hà Nội (HANU)", "cluster": "Thanh Xuân", "lat": 20.9885, "lng": 105.7942},
    {"name": "ĐH KHXH&NV / KHTN (VNU)", "cluster": "Thanh Xuân", "lat": 20.9990, "lng": 105.8090},
    {"name": "HV Bưu chính (PTIT)", "cluster": "Hà Đông", "lat": 20.9805, "lng": 105.7875},
    {"name": "ĐH Kiến trúc (HAU)", "cluster": "Hà Đông", "lat": 20.9825, "lng": 105.7895},
    {"name": "ĐH Thăng Long", "cluster": "Hoàng Mai", "lat": 20.9765, "lng": 105.8165},
    {"name": "ĐH Công nghiệp (HaUI)", "cluster": "Bắc Từ Liêm", "lat": 21.0542, "lng": 105.7355},
    {"name": "HV Tài chính (AOF)", "cluster": "Bắc Từ Liêm", "lat": 21.0745, "lng": 105.7725},
    {"name": "ĐH Mỏ - Địa chất (HUMG)", "cluster": "Bắc Từ Liêm", "lat": 21.0725, "lng": 105.7745},
]

# District name mapping dictionary
GADM_NAME_MAP = {
    'BaĐình': 'Ba Đình', 'HoànKiếm': 'Hoàn Kiếm', 'TâyHồ': 'Tây Hồ',
    'CầuGiấy': 'Cầu Giấy', 'ĐốngĐa': 'Đống Đa', 'HaiBàTrưng': 'Hai Bà Trưng',
    'HoàngMai': 'Hoàng Mai', 'ThanhXuân': 'Thanh Xuân', 'NamTừLiêm': 'Nam Từ Liêm',
    'BắcTừLiêm': 'Bắc Từ Liêm', 'HàĐông': 'Hà Đông', 'LongBiên': 'Long Biên',
    'GiaLâm': 'Gia Lâm', 'ĐôngAnh': 'Đông Anh', 'HoàiĐức': 'Hoài Đức',
    'ThanhTrì': 'Thanh Trì', 'ThườngTín': 'Thường Tín', 'ĐanPhượng': 'Đan Phượng',
    'ThạchThất': 'Thạch Thất', 'QuốcOai': 'Quốc Oai', 'ChươngMỹ': 'Chương Mỹ',
    'ThanhOai': 'Thanh Oai', 'MêLinh': 'Mê Linh', 'SócSơn': 'Sóc Sơn',
    'SơnTây': 'Sơn Tây', 'BaVì': 'Ba Vì', 'PhúXuyên': 'Phú Xuyên'
}

def load_data_and_base_layers():
    """Loads dataset, OSM vector roads, water layers, and filters out listings on water."""
    print("Loading vector roads and water...")
    G = ox.load_graphml(ROADS_PATH)
    gdf_edges = ox.graph_to_gdfs(G, nodes=False).to_crs(epsg=3857)
    gdf_water_4326 = gpd.read_file(WATER_PATH).to_crs(epsg=4326)
    gdf_water = gdf_water_4326.to_crs(epsg=3857)

    # Union of all water polygons for water filtering
    print("Building water spatial boundary mask...")
    water_polys_4326 = gdf_water_4326[gdf_water_4326.geom_type.isin(['Polygon', 'MultiPolygon'])].geometry.union_all()

    # Classify edges with Japanese Ink palette
    def get_road_style(highway):
        if isinstance(highway, list):
            highway = highway[0]
        highway = str(highway)
        if any(h in highway for h in ['motorway', 'trunk', 'primary']):
            return '#8E3A2B', 1.6, 4  # Terracotta / rust red
        elif any(h in highway for h in ['secondary', 'tertiary']):
            return '#504139', 0.9, 3  # Deep sumi charcoal
        else:
            return '#ADACA9', 0.4, 2  # Soft sumi grey

    styles = [get_road_style(h) for h in gdf_edges['highway']]
    gdf_edges['color'] = [s[0] for s in styles]
    gdf_edges['width'] = [s[1] for s in styles]
    gdf_edges['zorder'] = [s[2] for s in styles]

    # Calculate 16:9 landscape bounds
    min_lon, min_lat, max_lon, max_lat = 105.690, 20.940, 105.940, 21.090
    bbox_geom = gpd.GeoSeries([box(min_lon, min_lat, max_lon, max_lat)], crs='EPSG:4326').to_crs(epsg=3857).iloc[0]
    minx, miny, maxx, maxy = bbox_geom.bounds
    width, height = maxx - minx, maxy - miny
    new_width = height * (16.0 / 9.0)
    minx -= (new_width - width) / 2
    maxx += (new_width - width) / 2
    bounds = (minx, miny, maxx, maxy)

    # Load and clean listings
    print("Loading unified rental dataset...")
    df = pd.read_csv(DATA_PATH, low_memory=False)
    valid = df.dropna(subset=['latitude', 'longitude']).copy()
    initial_count = len(valid)

    # Filter out listings that fall on water bodies (West Lake, Red River, lakes)
    print("Filtering out listings on water bodies (West Lake, Red River, etc.)...")
    pts_geom = [Point(xy) for xy in zip(valid['longitude'], valid['latitude'])]
    gdf_pts = gpd.GeoDataFrame(valid, geometry=pts_geom, crs='EPSG:4326')
    is_on_water = gdf_pts.within(water_polys_4326)
    dropped_water_count = int(is_on_water.sum())
    valid = valid[~is_on_water].copy()
    print(f" Dropped {dropped_water_count:,} listings on water. Remaining valid land listings: {len(valid):,} / {initial_count:,}")

    # Project valid listings to EPSG:3857
    transformer = Transformer.from_crs('EPSG:4326', 'EPSG:3857', always_xy=True)
    xs, ys = transformer.transform(valid['longitude'].values, valid['latitude'].values)
    valid['x_3857'] = xs
    valid['y_3857'] = ys

    # Filter to visible landscape window
    visible = valid[(valid['x_3857'] >= minx) & (valid['x_3857'] <= maxx) & 
                    (valid['y_3857'] >= miny) & (valid['y_3857'] <= maxy)].copy()
    print(f" Listings visible in landscape window: {len(visible):,}")

    # Load district boundaries
    print("Loading district boundaries...")
    gdf_dist = gpd.read_file(DISTRICTS_PATH).to_crs(epsg=3857)
    gdf_dist['district_clean'] = gdf_dist['NAME_2'].map(GADM_NAME_MAP).fillna(gdf_dist['NAME_2'])

    # Compute district median price_per_m2 (from valid land listings)
    d_medians_m2 = valid.dropna(subset=['price_per_m2']).groupby('district')['price_per_m2'].median().to_dict()
    gdf_dist['median_price_per_m2'] = gdf_dist['district_clean'].map(d_medians_m2)

    return gdf_edges, gdf_water, visible, bounds, transformer, gdf_dist

def add_cartographic_elements(ax, bounds, include_compass=True):
    """Draws a minimalist Japanese sumi scale bar and optional north indicator."""
    minx, miny, maxx, maxy = bounds
    elements = []
    
    # Scale bar in bottom right (5 km = 5,000 meters)
    sb_x0 = maxx - 7000
    sb_y0 = miny + 800
    sb_len = 5000
    sb_h = 70
    
    # Background card for scale bar
    p_bg = ax.fill([sb_x0 - 500, sb_x0 + sb_len + 500, sb_x0 + sb_len + 500, sb_x0 - 500],
                   [sb_y0 - 450, sb_y0 - 450, sb_y0 + 450, sb_y0 + 450],
                   color='#FAF7F2', alpha=0.94, zorder=20, ec='#504139', lw=0.8)
    elements.extend(p_bg)
    
    # Segmented bar: 0 to 2.5 km (dark), 2.5 to 5 km (light)
    p_b1 = ax.fill([sb_x0, sb_x0 + 2500, sb_x0 + 2500, sb_x0],
                   [sb_y0, sb_y0, sb_y0 + sb_h, sb_y0 + sb_h],
                   color='#504139', zorder=21)
    elements.extend(p_b1)
    p_b2 = ax.fill([sb_x0 + 2500, sb_x0 + 5000, sb_x0 + 5000, sb_x0 + 2500],
                   [sb_y0, sb_y0, sb_y0 + sb_h, sb_y0 + sb_h],
                   color='#ADACA9', zorder=21, ec='#504139', lw=0.5)
    elements.extend(p_b2)
    
    t1 = ax.text(sb_x0, sb_y0 - 250, '0', fontsize=10, ha='center', va='top', color='#2C2523', fontweight='bold', zorder=22)
    t2 = ax.text(sb_x0 + 2500, sb_y0 - 250, '2.5', fontsize=10, ha='center', va='top', color='#2C2523', fontweight='bold', zorder=22)
    t3 = ax.text(sb_x0 + 5000, sb_y0 - 250, '5 km', fontsize=10, ha='center', va='top', color='#2C2523', fontweight='bold', zorder=22)
    t4 = ax.text(sb_x0 + 2500, sb_y0 + 200, 'EPSG:3857 | TRUE GEODESIC SCALE', fontsize=8.5, ha='center', va='bottom', color='#504139', zorder=22)
    elements.extend([t1, t2, t3, t4])

    # North indicator in top right
    compass_elements = []
    if include_compass:
        n_x = maxx - 1800
        n_y = maxy - 1500
        an = ax.annotate('', xy=(n_x, n_y + 600), xytext=(n_x, n_y),
                         arrowprops=dict(facecolor='#8E3A2B', edgecolor='#504139', width=2.0, headwidth=8, headlength=10),
                         zorder=22)
        tn = ax.text(n_x, n_y - 250, 'N', fontsize=13, ha='center', va='top', fontweight='bold', color='#8E3A2B', zorder=22)
        compass_elements.extend([an, tn])

    return elements, compass_elements

def main():
    gdf_edges, gdf_water, df, bounds, transformer, gdf_dist = load_data_and_base_layers()
    minx, miny, maxx, maxy = bounds

    # Initialize master base figure
    print("Initializing base vector canvas (3200x1800 @ 200 DPI)...")
    fig, ax = plt.subplots(figsize=(16, 9), dpi=200, facecolor='#FAF7F2')
    ax.set_facecolor('#FAF7F2')

    # Water bodies
    water_polys = gdf_water[gdf_water.geom_type.isin(['Polygon', 'MultiPolygon'])]
    water_lines = gdf_water[gdf_water.geom_type.isin(['LineString', 'MultiLineString'])]
    if not water_polys.empty:
        water_polys.plot(ax=ax, facecolor='#E3DEC3', edgecolor='#C4BEB1', linewidth=0.6, zorder=1)
    if not water_lines.empty:
        water_lines.plot(ax=ax, color='#C4BEB1', linewidth=0.8, zorder=1)

    # Road network hierarchy
    for z in [2, 3, 4]:
        sub = gdf_edges[gdf_edges['zorder'] == z]
        if not sub.empty:
            sub.plot(ax=ax, color=sub['color'], linewidth=sub['width'], zorder=z)

    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_axis_off()
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)

    # Add cartographic scale bar and north arrow
    sb_elements, compass_elements = add_cartographic_elements(ax, bounds)

    # 50% enlarged legend parameters
    LEG_FONTSIZE = 13.5
    LEG_TITLE_FONTSIZE = 15.5
    LEG_BORDERPAD = 1.2
    LEG_LABELSPACING = 0.7
    LEG_MARKERSCALE = 1.6

    def save_and_cleanup(filename, artists):
        out_path = os.path.join(FIGURES_DIR, filename)
        fig.savefig(out_path, dpi=200, facecolor='#FAF7F2', bbox_inches='tight', pad_inches=0)
        print(f" Saved: {out_path}")
        for art in artists:
            try:
                art.remove()
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Plot 02: Spatial Coverage & Data Quality Reconstruction
    # -------------------------------------------------------------------------
    print("Rendering Plot 02: Spatial Coverage & Data Quality...")
    artists = []
    sc = ax.scatter(df['x_3857'], df['y_3857'], c='#2A9D8F', s=14, alpha=0.55, zorder=5, edgecolors='none',
                    label=f'Central Urban Listings (N={len(df):,})')
    artists.append(sc)

    leg = ax.legend(loc='lower left', frameon=True, facecolor='#FAF7F2', edgecolor='#504139', framealpha=0.95,
                    fontsize=LEG_FONTSIZE, title='HANOI URBAN SPATIAL COVERAGE', title_fontsize=LEG_TITLE_FONTSIZE,
                    borderpad=LEG_BORDERPAD, labelspacing=LEG_LABELSPACING, markerscale=LEG_MARKERSCALE)
    leg.get_title().set_fontweight('bold')
    leg.get_title().set_color('#2C2523')
    artists.append(leg)
    save_and_cleanup("plot_02_spatial_regeneration_map.png", artists)

    # -------------------------------------------------------------------------
    # Plot 03: District Price Comparisons (Segmented by Border Data, Pink -> Red)
    # -------------------------------------------------------------------------
    print("Rendering Plot 03: District Price Comparison & Border Segmentation...")
    artists = []

    # -------------------------------------------------------------------------
    # Tiered District Grouping Palette:
    # Aggressive visual separation between tiers, with smooth yet distinct intra-group nuance:
    # 1. Hoàn Kiếm: Darkest blood cinnabar burgundy (#4C0519)
    # 2. Ba Đình, Tây Hồ: Deep dark garnet / wine reds (#881337 to #9F1239)
    # 3. Hai Bà Trưng, Cầu Giấy: Rich vivid ruby reds (#BE123C to #CE1848)
    # 4. Đống Đa, Nam Từ Liêm, Thanh Trì, Hoàng Mai, Thanh Xuân, Hà Đông: Warm crimson & punch reds (#E11D48 to #FB7185)
    # 5. Long Biên, Hoài Đức, Bắc Từ Liêm: Fresh vibrant rose/carnation pinks (#DB2777 to #F472B6)
    # 6. Peripheral / Suburban: Translucent pale blush pinks (#FBCFE8 to #FFF0F5)
    # -------------------------------------------------------------------------
    TIER_DEFINITIONS = [
        {
            'name': 'tier_hoankiem',
            'members': ['Hoàn Kiếm'],
            'colors': ['#4C0519', '#4C0519']
        },
        {
            'name': 'tier_upper',
            'members': ['Ba Đình', 'Tây Hồ'],
            'colors': ['#881337', '#9F1239']
        },
        {
            'name': 'tier_core',
            'members': ['Hai Bà Trưng', 'Cầu Giấy'],
            'colors': ['#BE123C', '#CE1848']
        },
        {
            'name': 'tier_inner',
            'members': ['Đống Đa', 'Nam Từ Liêm', 'Thanh Trì', 'Hoàng Mai', 'Thanh Xuân', 'Hà Đông'],
            'colors': ['#C8143C', '#F43F5E']
        },
        {
            'name': 'tier_outer',
            'members': ['Long Biên', 'Hoài Đức', 'Bắc Từ Liêm'],
            'colors': ['#DB2777', '#F472B6']
        },
        {
            'name': 'tier_suburban',
            'members': ['Gia Lâm', 'Thanh Oai', 'Sóc Sơn', 'Mê Linh', 'Chương Mỹ', 'Đông Anh', 'Đan Phượng', 'Quốc Oai'],
            'colors': ['#FBCFE8', '#FFF0F5']
        }
    ]

    # Precompute district-to-color lookup dictionary
    district_tier_color_map = {}
    for tier in TIER_DEFINITIONS:
        # Sort members by their actual median price_per_m2 descending so higher prices get darker shade in tier
        mems = tier['members']
        sub_series = gdf_dist.set_index('district_clean')['median_price_per_m2'].reindex(mems).dropna()
        sorted_mems = sub_series.sort_values(ascending=False).index.tolist()
        # Add any members that might be missing in data
        for m in mems:
            if m not in sorted_mems:
                sorted_mems.append(m)

        tier_cmap = LinearSegmentedColormap.from_list(tier['name'], tier['colors'])
        n = len(sorted_mems)
        for rank_i, d_name in enumerate(sorted_mems):
            # rank_i = 0 is highest price in group -> tier['colors'][0] (darker)
            interp_val = 0.0 if n == 1 else (rank_i / (n - 1))
            # Fine-tune: boost intensity of Thanh Xuan by nudging it towards deeper crimson
            if d_name == 'Thanh Xuân':
                interp_val = max(0.0, interp_val - 0.15)
            district_tier_color_map[d_name] = tier_cmap(interp_val)

    # Filter visible districts in bounding box
    dist_visible = gdf_dist[gdf_dist.geometry.intersects(box(minx, miny, maxx, maxy))].copy()

    # Assign tiered color
    dist_colors = []
    for d_name in dist_visible['district_clean']:
        c = district_tier_color_map.get(d_name, '#FFF0F5')
        dist_colors.append(c)
    dist_visible['fill_color'] = dist_colors

    # Plot segmented district polygons with crisp dark sumi borders and rich fill
    for _, row in dist_visible.iterrows():
        geom = row.geometry
        polys = [geom] if geom.geom_type == 'Polygon' else list(geom.geoms)
        for poly in polys:
            p_patch = ax.fill(*poly.exterior.xy, color=row['fill_color'], alpha=0.75, zorder=3.5)
            artists.extend(p_patch)
            b_line, = ax.plot(*poly.exterior.xy, color='#18181B', linewidth=2.3, zorder=4.5)
            artists.append(b_line)

        # Label district name clearly in center of polygon
        rep = row.geometry.representative_point()
        txt_x, txt_y = rep.x, rep.y
        if row['district_clean'] == 'Hà Đông':
            txt_x, txt_y = transformer.transform(105.782, 20.975)
        elif row['district_clean'] == 'Thanh Trì':
            txt_x, txt_y = transformer.transform(105.850, 20.940)

        if minx <= txt_x <= maxx and miny <= txt_y <= maxy:
            txt = ax.text(txt_x, txt_y, row['district_clean'].upper(), fontsize=11, fontweight='bold',
                          ha='center', va='center', color='#1E293B', zorder=12,
                          bbox=dict(boxstyle='round,pad=0.28', fc='#FAF7F2', ec='#475569', alpha=0.92, lw=0.8))
            artists.append(txt)

    # Subtle listing overlay
    sc_d = ax.scatter(df['x_3857'], df['y_3857'], c='#3E2723', s=9, alpha=0.32, zorder=5, edgecolors='none')
    artists.append(sc_d)

    # Plot 03 should NOT have a legend per user instruction
    save_and_cleanup("plot_03_district_distribution_map.png", artists)

    # -------------------------------------------------------------------------
    # Plot 04: Monthly Rental Price Tiers
    # -------------------------------------------------------------------------
    print("Rendering Plot 04: Rental Price Distribution...")
    artists = []
    p_tiers = [
        ("< 3.0M VND (Budget)", df['price_vnd'] < 3_000_000, '#2A9D8F', 14, 0.55),
        ("3.0M - 5.0M VND (Economy)", (df['price_vnd'] >= 3_000_000) & (df['price_vnd'] < 5_000_000), '#3A86FF', 16, 0.60),
        ("5.0M - 8.0M VND (Mid-Tier)", (df['price_vnd'] >= 5_000_000) & (df['price_vnd'] < 8_000_000), '#F4A261', 18, 0.65),
        ("8.0M - 12.0M VND (Upper-Mid)", (df['price_vnd'] >= 8_000_000) & (df['price_vnd'] < 12_000_000), '#E76F51', 20, 0.70),
        ("> 12.0M VND (High-End)", df['price_vnd'] >= 12_000_000, '#7209B7', 22, 0.75),
    ]
    for label, mask, color, s, a in p_tiers:
        sub = df[mask]
        sc = ax.scatter(sub['x_3857'], sub['y_3857'], c=color, s=s, alpha=a,
                        label=f"{label} (N={len(sub):,})", zorder=5, edgecolors='none')
        artists.append(sc)

    leg = ax.legend(loc='lower left', frameon=True, facecolor='#FAF7F2', edgecolor='#504139', framealpha=0.95,
                    fontsize=LEG_FONTSIZE, title='MONTHLY RENTAL PRICE TIERS', title_fontsize=LEG_TITLE_FONTSIZE,
                    borderpad=LEG_BORDERPAD, labelspacing=LEG_LABELSPACING, markerscale=LEG_MARKERSCALE)
    leg.get_title().set_fontweight('bold')
    leg.get_title().set_color('#2C2523')
    artists.append(leg)
    save_and_cleanup("plot_04_price_distribution_map.png", artists)

    # -------------------------------------------------------------------------
    # Plot 05: Usable Floor Area Tiers
    # -------------------------------------------------------------------------
    print("Rendering Plot 05: Floor Area Distribution...")
    artists = []
    a_tiers = [
        ("< 20 m² (Compact Studio)", df['area_m2'] < 20, '#06D6A0', 14, 0.55),
        ("20 - 30 m² (Standard Room)", (df['area_m2'] >= 20) & (df['area_m2'] < 30), '#118AB2', 16, 0.60),
        ("30 - 45 m² (Spacious 1BR/2BR)", (df['area_m2'] >= 30) & (df['area_m2'] < 45), '#FFD166', 18, 0.65),
        ("45 - 65 m² (Family Flat)", (df['area_m2'] >= 45) & (df['area_m2'] < 65), '#EF476F', 20, 0.70),
        ("> 65 m² (Multi-Room Residence)", df['area_m2'] >= 65, '#073B4C', 22, 0.75),
    ]
    for label, mask, color, s, a in a_tiers:
        sub = df[mask]
        sc = ax.scatter(sub['x_3857'], sub['y_3857'], c=color, s=s, alpha=a,
                        label=f"{label} (N={len(sub):,})", zorder=5, edgecolors='none')
        artists.append(sc)

    leg = ax.legend(loc='lower left', frameon=True, facecolor='#FAF7F2', edgecolor='#504139', framealpha=0.95,
                    fontsize=LEG_FONTSIZE, title='USABLE FLOOR AREA TIERS (m²)', title_fontsize=LEG_TITLE_FONTSIZE,
                    borderpad=LEG_BORDERPAD, labelspacing=LEG_LABELSPACING, markerscale=LEG_MARKERSCALE)
    leg.get_title().set_fontweight('bold')
    leg.get_title().set_color('#2C2523')
    artists.append(leg)
    save_and_cleanup("plot_05_area_distribution_map.png", artists)

    # -------------------------------------------------------------------------
    # Plot 06: Price per Square Meter Tiers
    # -------------------------------------------------------------------------
    print("Rendering Plot 06: Price per m² Distribution...")
    artists = []
    m2_tiers = [
        ("< 120k VND/m² (High Value)", df['price_per_m2'] < 120_000, '#2B9348', 14, 0.55),
        ("120k - 180k VND/m² (Moderate)", (df['price_per_m2'] >= 120_000) & (df['price_per_m2'] < 180_000), '#0077B6', 16, 0.60),
        ("180k - 250k VND/m² (Median Core)", (df['price_per_m2'] >= 180_000) & (df['price_per_m2'] < 250_000), '#EE9B00', 18, 0.65),
        ("250k - 350k VND/m² (Premium Hub)", (df['price_per_m2'] >= 250_000) & (df['price_per_m2'] < 350_000), '#CA6702', 20, 0.70),
        ("> 350k VND/m² (Ultra-Dense Core)", df['price_per_m2'] >= 350_000, '#9B2226', 22, 0.75),
    ]
    for label, mask, color, s, a in m2_tiers:
        sub = df[mask]
        sc = ax.scatter(sub['x_3857'], sub['y_3857'], c=color, s=s, alpha=a,
                        label=f"{label} (N={len(sub):,})", zorder=5, edgecolors='none')
        artists.append(sc)

    leg = ax.legend(loc='lower left', frameon=True, facecolor='#FAF7F2', edgecolor='#504139', framealpha=0.95,
                    fontsize=LEG_FONTSIZE, title='PRICE PER SQUARE METER (VND/m²)', title_fontsize=LEG_TITLE_FONTSIZE,
                    borderpad=LEG_BORDERPAD, labelspacing=LEG_LABELSPACING, markerscale=LEG_MARKERSCALE)
    leg.get_title().set_fontweight('bold')
    leg.get_title().set_color('#2C2523')
    artists.append(leg)
    save_and_cleanup("plot_06_price_per_m2_map.png", artists)

    # -------------------------------------------------------------------------
    # Plot 07: Accommodation Typology Breakdown
    # -------------------------------------------------------------------------
    print("Rendering Plot 07: House Type Typology...")
    artists = []
    top_types = df['house_type'].value_counts().head(5).index.tolist()
    t_palette = ['#2563EB', '#059669', '#EA580C', '#7C3AED', '#DB2777']
    t_colors = {t: t_palette[i] for i, t in enumerate(top_types)}

    for t in top_types:
        sub = df[df['house_type'] == t]
        sc = ax.scatter(sub['x_3857'], sub['y_3857'], c=t_colors[t], s=16, alpha=0.65,
                        label=f"{t} ({len(sub):,})", zorder=5, edgecolors='none')
        artists.append(sc)

    other_t = df[~df['house_type'].isin(top_types)]
    if not other_t.empty:
        sc = ax.scatter(other_t['x_3857'], other_t['y_3857'], c='#64748B', s=12, alpha=0.4,
                        label=f"Khác ({len(other_t):,})", zorder=4.5, edgecolors='none')
        artists.append(sc)

    leg = ax.legend(loc='lower left', frameon=True, facecolor='#FAF7F2', edgecolor='#504139', framealpha=0.95,
                    fontsize=LEG_FONTSIZE, title='PROPERTY TYPOLOGY BREAKDOWN', title_fontsize=LEG_TITLE_FONTSIZE,
                    borderpad=LEG_BORDERPAD, labelspacing=LEG_LABELSPACING, markerscale=LEG_MARKERSCALE)
    leg.get_title().set_fontweight('bold')
    leg.get_title().set_color('#2C2523')
    artists.append(leg)
    save_and_cleanup("plot_07_house_type_distribution_map.png", artists)

    # -------------------------------------------------------------------------
    # Plot 08: Furnishing & Amenity Prevalence
    # -------------------------------------------------------------------------
    print("Rendering Plot 08: Amenities Prevalence...")
    artists = []
    amenity_tiers = [
        ("Full nội thất cao cấp (≥ 6 tiện ích)", df['amenity_count'] >= 6, '#059669', 20, 0.75),
        ("Nội thất tốt (4 - 5 tiện ích)", (df['amenity_count'] >= 4) & (df['amenity_count'] < 6), '#3B82F6', 16, 0.60),
        ("Tiện ích cơ bản (2 - 3 tiện ích)", (df['amenity_count'] >= 2) & (df['amenity_count'] < 4), '#F59E0B', 14, 0.50),
        ("Phòng mộc / Tối giản (0 - 1 tiện ích)", df['amenity_count'] < 2, '#94A3B8', 12, 0.40),
    ]
    for label, mask, color, s, a in amenity_tiers:
        sub = df[mask]
        sc = ax.scatter(sub['x_3857'], sub['y_3857'], c=color, s=s, alpha=a,
                        label=f"{label} (N={len(sub):,})", zorder=5, edgecolors='none')
        artists.append(sc)

    leg = ax.legend(loc='lower left', frameon=True, facecolor='#FAF7F2', edgecolor='#504139', framealpha=0.95,
                    fontsize=LEG_FONTSIZE, title='AMENITY & FURNISHING PENETRATION', title_fontsize=LEG_TITLE_FONTSIZE,
                    borderpad=LEG_BORDERPAD, labelspacing=LEG_LABELSPACING, markerscale=LEG_MARKERSCALE)
    leg.get_title().set_fontweight('bold')
    leg.get_title().set_color('#2C2523')
    artists.append(leg)
    save_and_cleanup("plot_08_amenities_prevalence_map.png", artists)

    # -------------------------------------------------------------------------
    # Plot 09: Urban Mass Transit (Metro Lines 2A & 3 Corridors)
    # -------------------------------------------------------------------------
    print("Rendering Plot 09: Metro Transit Proximity...")
    artists = []

    m_lons = [st['lng'] for st in METRO_STATIONS]
    m_lats = [st['lat'] for st in METRO_STATIONS]
    m_xs, m_ys = transformer.transform(m_lons, m_lats)

    line2a_idx = [i for i, st in enumerate(METRO_STATIONS) if st['line'] == 'Line 2A']
    line3_idx = [i for i, st in enumerate(METRO_STATIONS) if st['line'] == 'Line 3']

    # Draw metro routes
    l2a_line, = ax.plot([m_xs[i] for i in line2a_idx], [m_ys[i] for i in line2a_idx],
                        color='#059669', linewidth=3.5, zorder=8, label='Metro Line 2A (Cát Linh - Hà Đông)')
    artists.append(l2a_line)

    l3_line, = ax.plot([m_xs[i] for i in line3_idx], [m_ys[i] for i in line3_idx],
                       color='#D97706', linewidth=3.5, zorder=8, label='Metro Line 3 (Nhổn - Cầu Giấy)')
    artists.append(l3_line)

    # Draw station points & 500m / 1000m buffers
    for x, y, st in zip(m_xs, m_ys, METRO_STATIONS):
        c1000 = plt.Circle((x, y), 1000, color='#10B981', fill=True, alpha=0.06, zorder=6)
        ax.add_patch(c1000)
        artists.append(c1000)

        c500 = plt.Circle((x, y), 500, color='#059669', fill=True, alpha=0.12, zorder=7)
        ax.add_patch(c500)
        artists.append(c500)

        st_sc = ax.scatter([x], [y], c='#FFFFFF', edgecolors='#8E3A2B', s=55, linewidth=2.0, zorder=12)
        artists.append(st_sc)

        txt = ax.text(x + 130, y + 130, st['name'], fontsize=8.5, fontweight='bold', color='#1E293B',
                      zorder=13, bbox=dict(boxstyle='round,pad=0.2', fc='#FAF7F2', ec='#CBD5E1', alpha=0.88, lw=0.6))
        artists.append(txt)

    # Listings colored by walkability
    metro_tiers = [
        ("< 500m (Đi bộ dễ dàng < 6 phút)", df['distance_to_nearest_metro_km'] <= 0.5, '#DC2626', 20, 0.80),
        ("500m - 1.0km (Vùng tiếp cận 6-12 phút)", (df['distance_to_nearest_metro_km'] > 0.5) & (df['distance_to_nearest_metro_km'] <= 1.0), '#F59E0B', 16, 0.65),
        ("1.0km - 2.0km (Xe đạp / Feeder Bus)", (df['distance_to_nearest_metro_km'] > 1.0) & (df['distance_to_nearest_metro_km'] <= 2.0), '#3B82F6', 12, 0.45),
        ("> 2.0km (Khu vực ngoài Metro)", df['distance_to_nearest_metro_km'] > 2.0, '#94A3B8', 10, 0.25),
    ]
    for label, mask, color, s, a in metro_tiers:
        sub = df[mask]
        sc = ax.scatter(sub['x_3857'], sub['y_3857'], c=color, s=s, alpha=a,
                        label=f"{label} (N={len(sub):,})", zorder=5, edgecolors='none')
        artists.append(sc)

    # Temporarily remove compass for Plot 09 per user instruction
    for comp_art in compass_elements:
        try:
            comp_art.remove()
        except Exception:
            pass

    leg = ax.legend(loc='upper right', frameon=True, facecolor='#FAF7F2', edgecolor='#504139', framealpha=0.95,
                    fontsize=LEG_FONTSIZE, title='METRO ACCESSIBILITY & BUFFER CATCHMENTS', title_fontsize=LEG_TITLE_FONTSIZE,
                    borderpad=LEG_BORDERPAD, labelspacing=LEG_LABELSPACING, markerscale=LEG_MARKERSCALE)
    leg.get_title().set_fontweight('bold')
    leg.get_title().set_color('#2C2523')
    artists.append(leg)
    save_and_cleanup("plot_09_metro_proximity_map.png", artists)

    # Re-add compass for subsequent maps
    _, compass_elements = add_cartographic_elements(ax, bounds, include_compass=True)

    # -------------------------------------------------------------------------
    # Plot 10: True Cost of Living (Rent + Normalized Utilities)
    # -------------------------------------------------------------------------
    print("Rendering Plot 10: True Cost of Living...")
    artists = []
    cost_col = 'estimated_total_living_cost' if 'estimated_total_living_cost' in df.columns else 'price_vnd'
    cost_tiers = [
        ("< 4.0M VND (Sinh viên / Tiết kiệm)", df[cost_col] < 4_000_000, '#1B4332', 14, 0.55),
        ("4.0M - 6.5M VND (Phổ thông)", (df[cost_col] >= 4_000_000) & (df[cost_col] < 6_500_000), '#1D3557', 16, 0.60),
        ("6.5M - 10.0M VND (Trung cấp)", (df[cost_col] >= 6_500_000) & (df[cost_col] < 10_000_000), '#D97706', 18, 0.65),
        ("10.0M - 15.0M VND (Cao cấp)", (df[cost_col] >= 10_000_000) & (df[cost_col] < 15_000_000), '#B91C1C', 20, 0.70),
        ("> 15.0M VND (Hạng sang)", df[cost_col] >= 15_000_000, '#581C87', 22, 0.75),
    ]
    for label, mask, color, s, a in cost_tiers:
        sub = df[mask]
        sc = ax.scatter(sub['x_3857'], sub['y_3857'], c=color, s=s, alpha=a,
                        label=f"{label} (N={len(sub):,})", zorder=5, edgecolors='none')
        artists.append(sc)

    leg = ax.legend(loc='lower left', frameon=True, facecolor='#FAF7F2', edgecolor='#504139', framealpha=0.95,
                    fontsize=LEG_FONTSIZE, title='TRUE MONTHLY LIVING COST (RENT + UTILITIES)', title_fontsize=LEG_TITLE_FONTSIZE,
                    borderpad=LEG_BORDERPAD, labelspacing=LEG_LABELSPACING, markerscale=LEG_MARKERSCALE)
    leg.get_title().set_fontweight('bold')
    leg.get_title().set_color('#2C2523')
    artists.append(leg)
    save_and_cleanup("plot_10_true_living_cost_map.png", artists)

    # -------------------------------------------------------------------------
    # Plot 11: Hedonic Value-Score Intelligence (Bargains vs Surcharges)
    # -------------------------------------------------------------------------
    print("Rendering Plot 11: Value-Score Intelligence...")
    artists = []
    val_tiers = [
        ("Giá hời - Đáng thuê nhất (Bargain < -15%)", df['market_value_tier'].str.contains('Giá hời', na=False), '#16A34A', 24, 0.85),
        ("Giá hợp lý (Fair Market ±15%)", df['market_value_tier'].str.contains('Giá hợp lý', na=False), '#64748B', 14, 0.45),
        ("Giá cao - Cần cân nhắc (Premium > +15%)", df['market_value_tier'].str.contains('Giá cao', na=False), '#DC2626', 20, 0.75),
    ]
    for label, mask, color, s, a in val_tiers:
        sub = df[mask]
        sc = ax.scatter(sub['x_3857'], sub['y_3857'], c=color, s=s, alpha=a,
                        label=f"{label} (N={len(sub):,})", zorder=6 if 'hời' in label else 5, edgecolors='none')
        artists.append(sc)

    other_val = df[~df['market_value_tier'].str.contains('Giá', na=False)]
    if not other_val.empty:
        sc = ax.scatter(other_val['x_3857'], other_val['y_3857'], c='#CBD5E1', s=10, alpha=0.3,
                        label=f"Chưa đủ dữ liệu (N={len(other_val):,})", zorder=4, edgecolors='none')
        artists.append(sc)

    leg = ax.legend(loc='lower left', frameon=True, facecolor='#FAF7F2', edgecolor='#504139', framealpha=0.95,
                    fontsize=LEG_FONTSIZE, title='HEDONIC VALUE-SCORE CLASSIFICATION', title_fontsize=LEG_TITLE_FONTSIZE,
                    borderpad=LEG_BORDERPAD, labelspacing=LEG_LABELSPACING, markerscale=LEG_MARKERSCALE)
    leg.get_title().set_fontweight('bold')
    leg.get_title().set_color('#2C2523')
    artists.append(leg)
    save_and_cleanup("plot_11_value_score_bargain_map.png", artists)

    # -------------------------------------------------------------------------
    # Plot 12: Higher Education & Student Housing Hubs
    # -------------------------------------------------------------------------
    print("Rendering Plot 12: University Proximity & Catchments...")
    artists = []

    u_lons = [u['lng'] for u in UNIVERSITIES]
    u_lats = [u['lat'] for u in UNIVERSITIES]
    u_xs, u_ys = transformer.transform(u_lons, u_lats)

    for x, y, u in zip(u_xs, u_ys, UNIVERSITIES):
        c1500 = plt.Circle((x, y), 1500, color='#F59E0B', fill=True, alpha=0.08, zorder=6)
        ax.add_patch(c1500)
        artists.append(c1500)

        u_sc = ax.scatter([x], [y], marker='^', c='#8E3A2B', edgecolors='#FAF7F2', s=95, linewidth=1.6, zorder=14)
        artists.append(u_sc)

        short_name = u['name'].split('(')[-1].replace(')', '') if '(' in u['name'] else u['name']
        txt = ax.text(x + 110, y + 110, short_name, fontsize=8.5, fontweight='bold', color='#78350F',
                      zorder=15, bbox=dict(boxstyle='round,pad=0.2', fc='#FEF3C7', ec='#F59E0B', alpha=0.90, lw=0.6))
        artists.append(txt)

    u_tiers = [
        ("< 500m (Vùng đi bộ sinh viên)", df['distance_to_nearest_university_km'] <= 0.5, '#7C3AED', 20, 0.80),
        ("500m - 1.0km (Bán kính vàng thuê trọ)", (df['distance_to_nearest_university_km'] > 0.5) & (df['distance_to_nearest_university_km'] <= 1.0), '#EC4899', 16, 0.65),
        ("1.0km - 2.0km (Vùng tiếp cận xe đạp/bus)", (df['distance_to_nearest_university_km'] > 1.0) & (df['distance_to_nearest_university_km'] <= 2.0), '#3B82F6', 12, 0.45),
        ("> 2.0km (Ngoài cụm đại học)", df['distance_to_nearest_university_km'] > 2.0, '#94A3B8', 10, 0.25),
    ]
    for label, mask, color, s, a in u_tiers:
        sub = df[mask]
        sc = ax.scatter(sub['x_3857'], sub['y_3857'], c=color, s=s, alpha=a,
                        label=f"{label} (N={len(sub):,})", zorder=5, edgecolors='none')
        artists.append(sc)

    leg = ax.legend(loc='lower left', frameon=True, facecolor='#FAF7F2', edgecolor='#504139', framealpha=0.95,
                    fontsize=LEG_FONTSIZE, title='UNIVERSITY HUBS & STUDENT CATCHMENTS (1.5km)', title_fontsize=LEG_TITLE_FONTSIZE,
                    borderpad=LEG_BORDERPAD, labelspacing=LEG_LABELSPACING, markerscale=LEG_MARKERSCALE)
    leg.get_title().set_fontweight('bold')
    leg.get_title().set_color('#2C2523')
    artists.append(leg)
    save_and_cleanup("plot_12_university_proximity_map.png", artists)

    plt.close()
    print("\nAll 11 Japanese Ink Native OSMnx Maps successfully re-rendered with updated specifications!")

if __name__ == "__main__":
    main()
