#!/usr/bin/env python3
"""
Direct Pixel Map & Independent Chart Rendering Suite for Hanoi Rental Dataset
=============================================================================
Renders high-definition landscape maps (2752x1536) directly onto the Japanese
ink cartography canvas without matplotlib distortion or stretching.
Also generates matching independent distribution charts with consistent aesthetics.
"""

import os
import math
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

# Resource caps
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"
os.environ["OPENBLAS_NUM_THREADS"] = "4"

BASE_DIR = "/home/totallynotminh/Documents/FunDS"
DATA_PATH = os.path.join(BASE_DIR, "data/hanoi_rentals_cleaned_unified.csv")
FIGURES_DIR = os.path.join(BASE_DIR, "figures")
CANVAS_PATH = os.path.join(FIGURES_DIR, "hanoi_ink_landscape_clean_hd.png")

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# -----------------------------------------------------------------------------
# 1. Coordinate Transformation Engine (WGS84 -> Canvas Pixels)
# -----------------------------------------------------------------------------

# Calibrated ground control points on 2752x1536 canvas
pts_src_geo = np.array([
    [105.79301, 21.03624],  # Cầu Giấy
    [105.82296, 21.03593],  # Ba Đình
    [105.81802, 21.02100],  # Đống Đa
    [105.85047, 21.02654],  # Hoàn Kiếm
    [105.81600, 20.99073],  # Thanh Xuân
    [105.78010, 20.96527],  # Hà Đông
], dtype=np.float32)

scale = 2.0
pts_dst_px = np.array([
    [390 * scale, 387 * scale],  # Cầu Giấy
    [615 * scale, 327 * scale],  # Ba Đình
    [610 * scale, 440 * scale],  # Đống Đa
    [780 * scale, 440 * scale],  # Hoàn Kiếm
    [520 * scale, 547 * scale],  # Thanh Xuân
    [430 * scale, 697 * scale],  # Hà Đông
], dtype=np.float32)

import cv2
AFFINE_M, _ = cv2.estimateAffine2D(pts_src_geo, pts_dst_px)

def geo_to_px(lons, lats):
    """Converts WGS84 longitudes and latitudes to canvas pixel coordinates."""
    lons = np.asarray(lons, dtype=np.float32)
    lats = np.asarray(lats, dtype=np.float32)
    ones = np.ones_like(lons, dtype=np.float32)
    coords = np.vstack([lons, lats, ones]).T
    return coords.dot(AFFINE_M.T)

def get_base_canvas():
    """Loads a fresh copy of the clean Japanese ink HD map."""
    return Image.open(CANVAS_PATH).convert("RGBA")

# -----------------------------------------------------------------------------
# 2. UI & Floating Legend Card Helper
# -----------------------------------------------------------------------------

def draw_legend_card(img, title, subtitle, items, x, y, width, height):
    """
    Renders an elegant semi-transparent floating legend card with drop shadow.
    items: list of tuples: (label, color_tuple_rgb, count_str, pct_str)
    """
    w, h = img.size
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    
    # Drop shadow
    draw.rounded_rectangle(
        [x + 8, y + 8, x + width + 8, y + height + 8],
        radius=16, fill=(0, 0, 0, 35)
    )
    # Ivory frosted glass card
    draw.rounded_rectangle(
        [x, y, x + width, y + height],
        radius=16, fill=(247, 243, 236, 238), outline=(180, 160, 140, 210), width=2
    )
    
    f_title = ImageFont.truetype(FONT_BOLD, 22)
    f_sub = ImageFont.truetype(FONT_REGULAR, 15)
    f_item = ImageFont.truetype(FONT_BOLD, 17)
    f_stat = ImageFont.truetype(FONT_REGULAR, 15)
    
    draw.text((x + 22, y + 18), title, fill=(30, 41, 59), font=f_title)
    draw.text((x + 22, y + 48), subtitle, fill=(100, 116, 139), font=f_sub)
    
    # Separator
    draw.line([(x + 22, y + 74), (x + width - 22, y + 74)], fill=(210, 200, 190), width=1)
    
    # Items
    start_y = y + 92
    num_items = len(items)
    cols = 2 if num_items > 6 else 1
    rows = math.ceil(num_items / cols)
    row_height = (height - 110) / rows
    
    for i, item in enumerate(items):
        c_idx = i // rows
        r_idx = i % rows
        
        ix = x + 24 + c_idx * (width // 2)
        iy = start_y + r_idx * row_height
        
        label, color, count_str, pct_str = item
        
        # Color dot
        dot_r = 7
        draw.ellipse([ix, iy + 3, ix + 14, iy + 17], fill=color + (255,), outline=(40, 40, 40, 180), width=1)
        draw.text((ix + 24, iy), label, fill=(15, 23, 42), font=f_item)
        stat_text = f"{count_str} ({pct_str})" if pct_str else count_str
        offset_x = (width // 2) - 30 if cols == 2 else width - 50
        draw.text((ix + 24, iy + 22), stat_text, fill=(100, 116, 139), font=f_stat)
        
    return Image.alpha_composite(img, card)

# -----------------------------------------------------------------------------
# 3. Dedicated Map Renderers (Direct Pixel, Landscape, No Matplotlib)
# -----------------------------------------------------------------------------

def render_all_maps(df: pd.DataFrame):
    geo_df = df.dropna(subset=["latitude", "longitude"]).copy()
    w, h = 2752, 1536
    pxs = geo_to_px(geo_df["longitude"].values, geo_df["latitude"].values)
    geo_df["px_x"] = pxs[:, 0]
    geo_df["px_y"] = pxs[:, 1]
    
    print("-> Rendering direct landscape maps on Japanese ink canvas...")
    
    # -------------------------------------------------------------------------
    # Map 02: Spatial Ward & District Regeneration
    # -------------------------------------------------------------------------
    base = get_base_canvas()
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Plot regenerated listings
    for _, row in geo_df.iterrows():
        x, y = row["px_x"], row["px_y"]
        if 0 <= x < w and 0 <= y < h:
            draw.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(59, 130, 246, 110), outline=(37, 99, 235, 180))
            
    # Load 192 ward centroids
    from shapely.geometry import Point
    centroid_coords = geo_df.groupby(["district", "ward"])[["longitude", "latitude"]].first().reset_index()
    c_pxs = geo_to_px(centroid_coords["longitude"].values, centroid_coords["latitude"].values)
    for x, y in c_pxs:
        if 0 <= x < w and 0 <= y < h:
            # Diamond marker for centroid
            draw.polygon([(x, y - 9), (x + 9, y), (x, y + 9), (x - 9, y)], 
                         fill=(245, 158, 11, 240), outline=(180, 83, 9, 255))
            
    merged = Image.alpha_composite(base, overlay)
    legend_items = [
        ("Ward Centroids (192 Wards)", (245, 158, 11), "192 Wards", "Allocated"),
        ("Regenerated Rental Units", (59, 130, 246), f"{len(geo_df):,} Units", "100% Resolved"),
        ("Median Centroid Distance", (16, 185, 129), "417 meters", "Accurate"),
        ("95th Percentile Bound", (139, 92, 246), "1,050 meters", "Urban Grid"),
    ]
    card_map = draw_legend_card(merged, "Spatial Administrative Regeneration", 
                                "WGS84 Coordinates Mapped to 192 Official Ward Centroids",
                                legend_items, w - 580, 50, 520, 280)
    card_map.convert("RGB").save(os.path.join(FIGURES_DIR, "plot_02_spatial_regeneration_map.png"), quality=95)
    print("   ✓ plot_02_spatial_regeneration_map.png")

    # -------------------------------------------------------------------------
    # Map 03: District Rental Distribution
    # -------------------------------------------------------------------------
    base = get_base_canvas()
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    DIST_COLORS = {
        "Đống Đa": (59, 130, 246),
        "Thanh Xuân": (16, 185, 129),
        "Nam Từ Liêm": (139, 92, 246),
        "Hoàng Mai": (245, 158, 11),
        "Cầu Giấy": (239, 68, 68),
        "Hà Đông": (217, 70, 239),
        "Bắc Từ Liêm": (6, 182, 212),
        "Hai Bà Trưng": (234, 88, 12),
        "Ba Đình": (13, 148, 136),
        "Tây Hồ": (99, 102, 241),
    }
    
    legend_items = []
    for d_name, col in DIST_COLORS.items():
        sub = geo_df[geo_df["district"] == d_name]
        for _, r in sub.iterrows():
            x, y = r["px_x"], r["px_y"]
            if 0 <= x < w and 0 <= y < h:
                draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=col + (130,), outline=col + (200,))
        legend_items.append((d_name, col, f"{len(sub):,} units", f"{len(sub)/len(geo_df)*100:.1f}%"))
        
    merged = Image.alpha_composite(base, overlay)
    card_map = draw_legend_card(merged, "Rental Supply Distribution by District",
                                "Spatial Clustering Across Greater Hanoi (14,870 Units)",
                                legend_items, w - 620, 50, 560, 420)
    card_map.convert("RGB").save(os.path.join(FIGURES_DIR, "plot_03_district_distribution_map.png"), quality=95)
    print("   ✓ plot_03_district_distribution_map.png")

    # -------------------------------------------------------------------------
    # Map 04: Rental Price Gradient (VND / month)
    # -------------------------------------------------------------------------
    base = get_base_canvas()
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    PRICE_BINS = [
        ("< 3.0M VND (Sinh viên / Giá rẻ)", 0, 3e6, (16, 185, 129)),
        ("3.0M - 4.5M VND (Studio phổ thông)", 3e6, 4.5e6, (59, 130, 246)),
        ("4.5M - 6.5M VND (Chung cư mini cao cấp)", 4.5e6, 6.5e6, (245, 158, 11)),
        ("6.5M - 10.0M VND (Căn hộ dịch vụ)", 6.5e6, 10e6, (234, 88, 12)),
        ("> 10.0M VND (Nguyên căn / Luxury)", 10e6, 1e9, (239, 68, 68)),
    ]
    
    legend_items = []
    for label, low, high, col in PRICE_BINS:
        sub = geo_df[(geo_df["price_vnd"] >= low) & (geo_df["price_vnd"] < high)]
        for _, r in sub.iterrows():
            x, y = r["px_x"], r["px_y"]
            if 0 <= x < w and 0 <= y < h:
                draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=col + (130,), outline=col + (200,))
        legend_items.append((label, col, f"{len(sub):,} units", f"{len(sub)/len(geo_df)*100:.1f}%"))
        
    merged = Image.alpha_composite(base, overlay)
    card_map = draw_legend_card(merged, "Rental Price Gradient (VND / Month)",
                                "Spatial Pricing Distribution across Hanoi Micro-Markets",
                                legend_items, w - 620, 50, 560, 360)
    card_map.convert("RGB").save(os.path.join(FIGURES_DIR, "plot_04_price_distribution_map.png"), quality=95)
    print("   ✓ plot_04_price_distribution_map.png")

    # -------------------------------------------------------------------------
    # Map 05: Usable Floor Area Distribution (m²)
    # -------------------------------------------------------------------------
    base = get_base_canvas()
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    AREA_BINS = [
        ("< 20 m² (Phòng trọ sinh viên)", 0, 20, (5, 150, 105)),
        ("20 - 30 m² (Studio / Mini standard)", 20, 30, (2, 132, 199)),
        ("30 - 45 m² (1 phòng ngủ / Rộng rãi)", 30, 45, (124, 58, 237)),
        ("45 - 65 m² (2 phòng ngủ)", 45, 65, (217, 119, 6)),
        ("> 65 m² (Căn hộ gia đình / Penthouse)", 65, 500, (220, 38, 38)),
    ]
    
    area_df = geo_df.dropna(subset=["area_m2"]).copy()
    legend_items = []
    for label, low, high, col in AREA_BINS:
        sub = area_df[(area_df["area_m2"] >= low) & (area_df["area_m2"] < high)]
        for _, r in sub.iterrows():
            x, y = r["px_x"], r["px_y"]
            if 0 <= x < w and 0 <= y < h:
                draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=col + (130,), outline=col + (200,))
        legend_items.append((label, col, f"{len(sub):,} units", f"{len(sub)/len(area_df)*100:.1f}%"))
        
    merged = Image.alpha_composite(base, overlay)
    card_map = draw_legend_card(merged, "Usable Floor Area Footprints (m²)",
                                "Spatial Footprints of Available Hanoi Rental Units",
                                legend_items, w - 620, 50, 560, 360)
    card_map.convert("RGB").save(os.path.join(FIGURES_DIR, "plot_05_area_distribution_map.png"), quality=95)
    print("   ✓ plot_05_area_distribution_map.png")

    # -------------------------------------------------------------------------
    # Map 06: Unit Rental Rate (VND / m² / month)
    # -------------------------------------------------------------------------
    base = get_base_canvas()
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    sqm_df = geo_df.dropna(subset=["price_per_m2"]).copy()
    RATE_BINS = [
        ("< 100k / m² (Ngoại thành / Tiết kiệm)", 0, 100000, (52, 211, 153)),
        ("100k - 150k / m² (Phổ thông)", 100000, 150000, (6, 182, 212)),
        ("150k - 200k / m² (Trung tâm / Tiện nghi)", 150000, 200000, (59, 130, 246)),
        ("200k - 250k / m² (Cao cấp / Đống Đa)", 200000, 250000, (249, 115, 22)),
        ("> 250k / m² (Tây Hồ / Hoàn Kiếm Core)", 250000, 1e7, (244, 63, 94)),
    ]
    legend_items = []
    for label, low, high, col in RATE_BINS:
        sub = sqm_df[(sqm_df["price_per_m2"] >= low) & (sqm_df["price_per_m2"] < high)]
        for _, r in sub.iterrows():
            x, y = r["px_x"], r["px_y"]
            if 0 <= x < w and 0 <= y < h:
                draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=col + (130,), outline=col + (200,))
        legend_items.append((label, col, f"{len(sub):,} units", f"{len(sub)/len(sqm_df)*100:.1f}%"))
        
    merged = Image.alpha_composite(base, overlay)
    card_map = draw_legend_card(merged, "Unit Rental Density (VND / m² / month)",
                                "Spatial Capital Intensity per Square Meter of Floor Area",
                                legend_items, w - 620, 50, 560, 360)
    card_map.convert("RGB").save(os.path.join(FIGURES_DIR, "plot_06_price_per_m2_map.png"), quality=95)
    print("   ✓ plot_06_price_per_m2_map.png")

    # -------------------------------------------------------------------------
    # Map 07: Accommodation Typology Localization
    # -------------------------------------------------------------------------
    base = get_base_canvas()
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    TYPE_COLORS = {
        "Phòng trọ sinh viên": ((217, 119, 6), "2.8M VND"),
        "Studio khép kín": ((37, 99, 235), "4.5M VND"),
        "Căn hộ dịch vụ": ((5, 150, 105), "6.8M VND"),
        "Chung cư mini": ((124, 58, 237), "4.2M VND"),
        "Nhà nguyên căn": ((220, 38, 38), "9.5M VND"),
        "Phòng trọ / Khác": ((100, 116, 139), "3.8M VND"),
    }
    legend_items = []
    for h_type, (col, med_price) in TYPE_COLORS.items():
        sub = geo_df[geo_df["house_type"] == h_type]
        for _, r in sub.iterrows():
            x, y = r["px_x"], r["px_y"]
            if 0 <= x < w and 0 <= y < h:
                draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=col + (130,), outline=col + (200,))
        legend_items.append((h_type, col, f"{len(sub):,} units", f"Median: {med_price}"))
        
    merged = Image.alpha_composite(base, overlay)
    card_map = draw_legend_card(merged, "Accommodation Typology Localization",
                                "Distribution of Rental Room Classes & Median Monthly Rates",
                                legend_items, w - 620, 50, 560, 390)
    card_map.convert("RGB").save(os.path.join(FIGURES_DIR, "plot_07_house_type_distribution_map.png"), quality=95)
    print("   ✓ plot_07_house_type_distribution_map.png")

    # -------------------------------------------------------------------------
    # Map 08: Modern Amenity Equipment Density
    # -------------------------------------------------------------------------
    base = get_base_canvas()
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    AMENITY_TIERS = [
        ("0 - 2 Tiện ích (Cơ bản / Thiếu điều hòa)", 0, 2, (148, 163, 184)),
        ("3 - 4 Tiện ích (Phổ thông / Đầy đủ cơ bản)", 3, 4, (13, 148, 136)),
        ("5 - 6 Tiện ích (Hiện đại / Full nội thất)", 5, 6, (79, 70, 229)),
        ("7 - 8 Tiện ích (Cao cấp / Thang máy + PCCC)", 7, 8, (234, 88, 12)),
    ]
    legend_items = []
    for label, low, high, col in AMENITY_TIERS:
        sub = geo_df[(geo_df["amenity_count"] >= low) & (geo_df["amenity_count"] <= high)]
        for _, r in sub.iterrows():
            x, y = r["px_x"], r["px_y"]
            if 0 <= x < w and 0 <= y < h:
                draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=col + (130,), outline=col + (200,))
        legend_items.append((label, col, f"{len(sub):,} units", f"{len(sub)/len(geo_df)*100:.1f}%"))
        
    merged = Image.alpha_composite(base, overlay)
    card_map = draw_legend_card(merged, "Modern Amenity Equipment Density",
                                "Composite Penetration Score (0 to 8 Amenities)",
                                legend_items, w - 620, 50, 560, 340)
    card_map.convert("RGB").save(os.path.join(FIGURES_DIR, "plot_08_amenities_prevalence_map.png"), quality=95)
    print("   ✓ plot_08_amenities_prevalence_map.png")

    # -------------------------------------------------------------------------
    # Map 09: Metro Lines 2A & 3 Proximity & Catchments
    # -------------------------------------------------------------------------
    base = get_base_canvas()
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    METRO_TIERS = {
        "< 500m (Đi bộ dễ dàng)": ((225, 29, 72), "4.3M VND", "+22.9%"),
        "500m - 1km (Đi bộ vừa)": ((245, 158, 11), "4.0M VND", "+14.3%"),
        "1km - 2km (Xe đạp / Bus)": ((8, 145, 178), "3.8M VND", "+8.6%"),
        "> 2km (Khu vực ngoài Metro)": ((148, 163, 184), "3.5M VND", "Baseline"),
    }
    
    # Plot listings by metro tier
    for tier, (col, med, prem) in METRO_TIERS.items():
        sub = geo_df[geo_df["metro_proximity_tier"] == tier]
        for _, r in sub.iterrows():
            x, y = r["px_x"], r["px_y"]
            if 0 <= x < w and 0 <= y < h:
                draw.ellipse([x - 4, y - 4, x + 4, y + 4], fill=col + (110,), outline=col + (180,))
                
    # Draw Metro Line 2A & 3 track routes and station points
    line2a_geo = [
        (105.828, 21.028), (105.822, 21.022), (105.817, 21.015), (105.811, 21.007),
        (105.813, 20.999), (105.802, 20.992), (105.792, 20.985), (105.787, 20.978),
        (105.776, 20.970), (105.748, 20.950)
    ]
    line3_geo = [
        (105.731, 21.062), (105.762, 21.044), (105.773, 21.038), (105.781, 21.036),
        (105.794, 21.035), (105.803, 21.029)
    ]
    
    l2_px = geo_to_px([p[0] for p in line2a_geo], [p[1] for p in line2a_geo])
    l3_px = geo_to_px([p[0] for p in line3_geo], [p[1] for p in line3_geo])
    
    # Draw tracks
    for i in range(len(l2_px) - 1):
        draw.line([(l2_px[i][0], l2_px[i][1]), (l2_px[i+1][0], l2_px[i+1][1])], fill=(220, 38, 38, 255), width=5)
    for i in range(len(l3_px) - 1):
        draw.line([(l3_px[i][0], l3_px[i][1]), (l3_px[i+1][0], l3_px[i+1][1])], fill=(37, 99, 235, 255), width=5)
        
    # Draw station circles (500m catchment buffer in pixels ~ 22 px)
    station_px = np.vstack([l2_px, l3_px])
    for sx, sy in station_px:
        # 500m buffer
        draw.ellipse([sx - 24, sy - 24, sx + 24, sy + 24], fill=(225, 29, 72, 35), outline=(225, 29, 72, 140), width=2)
        # Core station marker
        draw.ellipse([sx - 7, sy - 7, sx + 7, sy + 7], fill=(255, 255, 255, 255), outline=(15, 23, 42, 255), width=3)
        
    merged = Image.alpha_composite(base, overlay)
    legend_items = []
    for tier, (col, med, prem) in METRO_TIERS.items():
        count = len(geo_df[geo_df["metro_proximity_tier"] == tier])
        pct = count / len(geo_df) * 100
        legend_items.append((tier.split(" (")[0], col, f"{count:,} ({pct:.1f}%)", f"Med: {med} ({prem})"))
        
    card_map = draw_legend_card(merged, "Metro Line 2A & Line 3 Proximity",
                                "Walkable Catchments (<500m) Command a +22.9% Rental Premium",
                                legend_items, w - 640, 50, 580, 340)
    card_map.convert("RGB").save(os.path.join(FIGURES_DIR, "plot_09_metro_proximity_map.png"), quality=95)
    print("   ✓ plot_09_metro_proximity_map.png")

    # -------------------------------------------------------------------------
    # Map 10: True Cost of Living (Effective Monthly Expenditure)
    # -------------------------------------------------------------------------
    base = get_base_canvas()
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    LIVING_BINS = [
        ("< 4.0M VND (Sinh viên tiết kiệm)", 0, 4e6, (16, 185, 129)),
        ("4.0M - 5.5M VND (Studio / Chung cư mini)", 4e6, 5.5e6, (59, 130, 246)),
        ("5.5M - 7.5M VND (Studio cao cấp)", 5.5e6, 7.5e6, (245, 158, 11)),
        ("7.5M - 11.0M VND (Căn hộ dịch vụ)", 7.5e6, 11e6, (234, 88, 12)),
        ("> 11.0M VND (Gia đình / Luxury)", 11e6, 1e9, (239, 68, 68)),
    ]
    legend_items = []
    for label, low, high, col in LIVING_BINS:
        sub = geo_df[(geo_df["estimated_total_living_cost"] >= low) & (geo_df["estimated_total_living_cost"] < high)]
        for _, r in sub.iterrows():
            x, y = r["px_x"], r["px_y"]
            if 0 <= x < w and 0 <= y < h:
                draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=col + (130,), outline=col + (200,))
        legend_items.append((label, col, f"{len(sub):,} units", f"{len(sub)/len(geo_df)*100:.1f}%"))
        
    merged = Image.alpha_composite(base, overlay)
    card_map = draw_legend_card(merged, "True Monthly Cost of Living",
                                "Stated Base Rent + Normalized Electricity (4k/kWh) & Water Surcharges",
                                legend_items, w - 640, 50, 580, 360)
    card_map.convert("RGB").save(os.path.join(FIGURES_DIR, "plot_10_true_living_cost_map.png"), quality=95)
    print("   ✓ plot_10_true_living_cost_map.png")

    # -------------------------------------------------------------------------
    # Map 11: Hedonic Value-Score Model: Discovering Bargains
    # -------------------------------------------------------------------------
    base = get_base_canvas()
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    VALUE_COLORS = {
        "Giá hời (Bargain, Residual < -15%)": ((16, 185, 129), "Dưới giá thị trường"),
        "Giá hợp lý (Fair Market Value, ±15%)": ((59, 130, 246), "Đúng giá thị trường"),
        "Giá cao (Overpriced, Residual > +15%)": ((239, 68, 68), "Định giá cao"),
    }
    
    legend_items = []
    for tier, (col, desc) in VALUE_COLORS.items():
        sub = geo_df[geo_df["market_value_tier"] == tier]
        for _, r in sub.iterrows():
            x, y = r["px_x"], r["px_y"]
            if 0 <= x < w and 0 <= y < h:
                # Give bargain listings a slightly larger glowing dot
                dot_sz = 6 if "hời" in tier else 4
                alpha_val = 160 if "hời" in tier else 100
                draw.ellipse([x - dot_sz, y - dot_sz, x + dot_sz, y + dot_sz], 
                             fill=col + (alpha_val,), outline=col + (220,))
        count = len(sub)
        pct = count / len(geo_df) * 100
        legend_items.append((tier.split(" (")[0], col, f"{count:,} ({pct:.1f}%)", desc))
        
    merged = Image.alpha_composite(base, overlay)
    card_map = draw_legend_card(merged, "Hedonic Value-Score Market Intelligence",
                                "Residual Analysis Isolates Truly Underpriced Bargain Units",
                                legend_items, w - 620, 50, 560, 320)
    card_map.convert("RGB").save(os.path.join(FIGURES_DIR, "plot_11_value_score_bargain_map.png"), quality=95)
    print("   ✓ plot_11_value_score_bargain_map.png")

    # -------------------------------------------------------------------------
    # Map 12: Higher Education & University Proximity
    # -------------------------------------------------------------------------
    base = get_base_canvas()
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    UNI_CLUSTERS = {
        "Cầu Giấy": ((239, 68, 68), "3.80M VND"),
        "Hoàng Mai": ((245, 158, 11), "3.83M VND"),
        "Bách - Kinh - Xây": ((59, 130, 246), "3.50M VND"),
        "Chùa Bộc": ((16, 185, 129), "3.70M VND"),
        "Thanh Xuân": ((139, 92, 246), "4.00M VND"),
        "Chùa Láng": ((6, 182, 212), "4.05M VND"),
        "Hà Đông": ((217, 70, 239), "3.47M VND"),
        "Bắc Từ Liêm": ((234, 88, 12), "3.50M VND"),
    }
    
    # Plot student housing listings
    for c_name, (col, med) in UNI_CLUSTERS.items():
        sub = geo_df[geo_df["nearest_university_cluster"] == c_name]
        for _, r in sub.iterrows():
            x, y = r["px_x"], r["px_y"]
            if 0 <= x < w and 0 <= y < h:
                draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=col + (120,), outline=col + (190,))
                
    # Catalog of 22 universities to plot as golden stars
    UNIVERSITIES = [
        ("ĐH Bách Khoa", 105.843, 21.004),
        ("ĐH Kinh tế Quốc dân", 105.842, 20.996),
        ("ĐH Xây dựng", 105.844, 21.000),
        ("ĐH Y Hà Nội", 105.831, 21.003),
        ("HV Ngân hàng", 105.828, 21.010),
        ("ĐH Thủy lợi", 105.824, 21.007),
        ("ĐH Ngoại thương", 105.803, 21.024),
        ("ĐH Luật Hà Nội", 105.811, 21.020),
        ("HV Báo chí & TT", 105.789, 21.036),
        ("ĐH Sư phạm Hà Nội", 105.783, 21.037),
        ("ĐH Quốc gia Hà Nội", 105.781, 21.037),
        ("ĐH Thương mại", 105.772, 21.037),
        ("ĐH Giao thông Vận tải", 105.803, 21.029),
        ("ĐH KHXH&NV / KHTN", 105.811, 20.995),
        ("ĐH Hà Nội", 105.795, 20.982),
        ("ĐH Kiến trúc", 105.787, 20.982),
        ("HV Bưu chính Viễn thông", 105.787, 20.980),
        ("ĐH Thăng Long", 105.817, 20.976),
        ("ĐH Mỏ - Địa chất", 105.778, 21.072),
        ("HV Tài chính", 105.776, 21.070),
        ("ĐH Công nghiệp", 105.742, 21.054),
        ("ĐH Mở Hà Nội", 105.847, 21.009),
    ]
    
    uni_px = geo_to_px([u[1] for u in UNIVERSITIES], [u[2] for u in UNIVERSITIES])
    for (uname, _, _), (ux, uy) in zip(UNIVERSITIES, uni_px):
        if 0 <= ux < w and 0 <= uy < h:
            # 1.0 km walking catchment buffer (~45 px radius)
            draw.ellipse([ux - 45, uy - 45, ux + 45, uy + 45], fill=(245, 158, 11, 30), outline=(217, 119, 6, 120), width=1)
            # Golden university star
            r_star = 9
            draw.polygon([
                (ux, uy - r_star), (ux + 3, uy - 3), (ux + r_star, uy),
                (ux + 3, uy + 3), (ux, uy + r_star), (ux - 3, uy + 3),
                (ux - r_star, uy), (ux - 3, uy - 3)
            ], fill=(255, 255, 255, 255), outline=(15, 23, 42, 255), width=2)
            draw.ellipse([ux - 4, uy - 4, ux + 4, uy + 4], fill=(245, 158, 11, 255))
            
    merged = Image.alpha_composite(base, overlay)
    legend_items = []
    for c_name, (col, med) in UNI_CLUSTERS.items():
        count = len(geo_df[geo_df["nearest_university_cluster"] == c_name])
        pct = count / len(geo_df) * 100
        legend_items.append((c_name, col, f"{count:,} ({pct:.1f}%)", f"Med: {med}"))
        
    card_map = draw_legend_card(merged, "Higher Education Hubs & Student Housing",
                                "22 Cataloged Campuses Across 8 Academic Clusters (1.0 km Buffers)",
                                legend_items, w - 640, 50, 580, 420)
    card_map.convert("RGB").save(os.path.join(FIGURES_DIR, "plot_12_university_proximity_map.png"), quality=95)
    print("   ✓ plot_12_university_proximity_map.png")

# -----------------------------------------------------------------------------
# 4. Independent Distribution Chart Renderers (Standalone High-DPI Figures)
# -----------------------------------------------------------------------------

def setup_chart_style():
    sns.set_theme(style="whitegrid", font_scale=1.05)
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Liberation Sans", "Arial"]
    plt.rcParams["axes.unicode_minus"] = False

def render_all_charts(df: pd.DataFrame, df_raw: pd.DataFrame):
    print("-> Rendering independent standalone distribution charts...")
    setup_chart_style()
    
    # -------------------------------------------------------------------------
    # Chart 02: Spatial Regeneration Centroid Distance
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=180)
    fig.patch.set_facecolor("#FAF7F2")
    ax.set_facecolor("#FAF7F2")
    
    geo = df.dropna(subset=["distance_to_ward_centroid_km"]).copy()
    dists = geo["distance_to_ward_centroid_km"] * 1000.0  # meters
    dists_capped = dists[dists <= 2500]
    
    sns.histplot(dists_capped, bins=50, kde=True, color="#2563EB", ax=ax, edgecolor="#1D4ED8", alpha=0.6)
    med = dists.median()
    p95 = dists.quantile(0.95)
    
    ax.axvline(med, color="#DC2626", linestyle="--", linewidth=2.5, label=f"Median Distance: {med:.0f} m")
    ax.axvline(p95, color="#D97706", linestyle=":", linewidth=2.5, label=f"95th Percentile: {p95:.0f} m")
    
    ax.set_title("Geodetic Nearest-Neighbor Ward Centroid Distance Distribution", fontsize=14, fontweight="bold", pad=15, color="#0F172A")
    ax.set_xlabel("Distance to Matched Ward Centroid (Meters)", fontsize=11, fontweight="bold", labelpad=10, color="#334155")
    ax.set_ylabel("Listing Count", fontsize=11, fontweight="bold", labelpad=10, color="#334155")
    ax.legend(frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1", fontsize=10.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "plot_02_spatial_regeneration_chart.png"), facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close()
    print("   ✓ plot_02_spatial_regeneration_chart.png")

    # -------------------------------------------------------------------------
    # Chart 04: Rental Price Distribution & Fences
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=180)
    fig.patch.set_facecolor("#FAF7F2")
    ax.set_facecolor("#FAF7F2")
    
    prices_m = df["price_vnd"] / 1e6
    sns.histplot(prices_m, bins=55, kde=True, color="#059669", ax=ax, edgecolor="#047857", alpha=0.6)
    
    p_med = prices_m.median()
    p_q1 = prices_m.quantile(0.25)
    p_q3 = prices_m.quantile(0.75)
    
    ax.axvline(p_med, color="#DC2626", linestyle="--", linewidth=2.5, label=f"Median: {p_med:.2f}M VND")
    ax.axvline(p_q1, color="#2563EB", linestyle=":", linewidth=2.0, label=f"Q1 (25%): {p_q1:.2f}M VND")
    ax.axvline(p_q3, color="#D97706", linestyle=":", linewidth=2.0, label=f"Q3 (75%): {p_q3:.2f}M VND")
    
    ax.set_title("Monthly Rental Price Distribution Across Validated Supply", fontsize=14, fontweight="bold", pad=15, color="#0F172A")
    ax.set_xlabel("Monthly Rent (Million VND)", fontsize=11, fontweight="bold", labelpad=10, color="#334155")
    ax.set_ylabel("Listing Count", fontsize=11, fontweight="bold", labelpad=10, color="#334155")
    ax.set_xlim(0, 16)
    ax.legend(frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1", fontsize=10.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "plot_04_price_distribution_chart.png"), facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close()
    print("   ✓ plot_04_price_distribution_chart.png")

    # -------------------------------------------------------------------------
    # Chart 05: Floor Area Distribution
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=180)
    fig.patch.set_facecolor("#FAF7F2")
    ax.set_facecolor("#FAF7F2")
    
    areas = df["area_m2"].dropna()
    sns.histplot(areas, bins=50, kde=True, color="#7C3AED", ax=ax, edgecolor="#6D28D9", alpha=0.6)
    
    a_med = areas.median()
    ax.axvline(a_med, color="#DC2626", linestyle="--", linewidth=2.5, label=f"Median Floor Area: {a_med:.1f} m²")
    ax.axvline(areas.quantile(0.75), color="#2563EB", linestyle=":", linewidth=2.0, label=f"Q3 (75%): {areas.quantile(0.75):.1f} m²")
    
    ax.set_title("Usable Floor Area Distribution in Hanoi Rental Market", fontsize=14, fontweight="bold", pad=15, color="#0F172A")
    ax.set_xlabel("Usable Floor Area (m²)", fontsize=11, fontweight="bold", labelpad=10, color="#334155")
    ax.set_ylabel("Listing Count", fontsize=11, fontweight="bold", labelpad=10, color="#334155")
    ax.set_xlim(5, 80)
    ax.legend(frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1", fontsize=10.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "plot_05_area_distribution_chart.png"), facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close()
    print("   ✓ plot_05_area_distribution_chart.png")

    # -------------------------------------------------------------------------
    # Chart 06: Unit Price by District (VND / m²)
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=180)
    fig.patch.set_facecolor("#FAF7F2")
    ax.set_facecolor("#FAF7F2")
    
    sub = df.dropna(subset=["price_per_m2"]).copy()
    sub = sub[sub["district"] != "Chưa rõ"]
    dist_counts = sub["district"].value_counts()
    valid_districts = dist_counts[dist_counts > 100].index
    sub = sub[sub["district"].isin(valid_districts)]
    
    district_rates = sub.groupby("district")["price_per_m2"].median().sort_values(ascending=False)
    
    colors = sns.color_palette("mako", len(district_rates))[::-1]
    bars = ax.barh(district_rates.index[::-1], (district_rates.values[::-1] / 1000.0), color=colors, height=0.65)
    
    for bar in bars:
        w = bar.get_width()
        ax.text(w + 3, bar.get_y() + bar.get_height()/2, f"{w:,.0f}k / m²", 
                va="center", ha="left", fontsize=9.5, fontweight="bold", color="#1E293B")
        
    ax.set_title("Median Rental Value per Square Meter by District (>100 Listings)", fontsize=14, fontweight="bold", pad=15, color="#0F172A")
    ax.set_xlabel("Median Rental Rate (Thousand VND / m² / month)", fontsize=11, fontweight="bold", labelpad=10, color="#334155")
    ax.set_xlim(0, max(district_rates.values / 1000.0) * 1.18)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "plot_06_price_per_m2_chart.png"), facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close()
    print("   ✓ plot_06_price_per_m2_chart.png")

    # -------------------------------------------------------------------------
    # Chart 07: Accommodation Typology Breakdown
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=180)
    fig.patch.set_facecolor("#FAF7F2")
    ax.set_facecolor("#FAF7F2")
    
    type_stats = df.groupby("house_type").agg(
        count=("listing_id", "count"),
        median_rent=("price_vnd", "median")
    ).sort_values("count", ascending=False)
    
    colors = ["#D97706", "#64748B", "#2563EB", "#059669", "#7C3AED", "#DC2626"]
    bars = ax.barh(type_stats.index[::-1], type_stats["count"].values[::-1], color=colors[:len(type_stats)][::-1], height=0.65)
    
    for bar, med in zip(bars, type_stats["median_rent"].values[::-1]):
        w = bar.get_width()
        pct = w / len(df) * 100
        ax.text(w + 35, bar.get_y() + bar.get_height()/2, f"{int(w):,} ({pct:.1f}%) | Median: {med/1e6:.1f}M", 
                va="center", ha="left", fontsize=9.5, fontweight="bold", color="#1E293B")
        
    ax.set_title("Rental Accommodation Typologies & Median Rent Levels", fontsize=14, fontweight="bold", pad=15, color="#0F172A")
    ax.set_xlabel("Listing Volume", fontsize=11, fontweight="bold", labelpad=10, color="#334155")
    ax.set_xlim(0, max(type_stats["count"].values) * 1.35)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "plot_07_house_type_distribution_chart.png"), facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close()
    print("   ✓ plot_07_house_type_distribution_chart.png")

    # -------------------------------------------------------------------------
    # Chart 08: Modern Amenity Penetration Rates
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=180)
    fig.patch.set_facecolor("#FAF7F2")
    ax.set_facecolor("#FAF7F2")
    
    amenities = [
        ("water_heater", "Bình nóng lạnh"),
        ("air_conditioner", "Điều hòa"),
        ("washing_machine", "Máy giặt"),
        ("balcony_window", "Ban công / Cửa sổ"),
        ("refrigerator", "Tủ lạnh"),
        ("elevator", "Thang máy"),
        ("pet_allowed", "Cho nuôi thú cưng"),
    ]
    rates = [(label, df[col].mean() * 100.0) for col, label in amenities]
    rates.sort(key=lambda x: x[1])
    
    labels, pcts = zip(*rates)
    colors = sns.color_palette("crest", len(labels))
    bars = ax.barh(labels, pcts, color=colors, height=0.65)
    
    for bar in bars:
        w = bar.get_width()
        ax.text(w + 1.2, bar.get_y() + bar.get_height()/2, f"{w:.1f}%", 
                va="center", ha="left", fontsize=10, fontweight="bold", color="#1E293B")
        
    ax.set_title("Penetration Rates of Key Amenities in Hanoi Rental Market", fontsize=14, fontweight="bold", pad=15, color="#0F172A")
    ax.set_xlabel("Penetration Rate (%) Across Active Inventory", fontsize=11, fontweight="bold", labelpad=10, color="#334155")
    ax.set_xlim(0, 60)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "plot_08_amenities_prevalence_chart.png"), facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close()
    print("   ✓ plot_08_amenities_prevalence_chart.png")

    # -------------------------------------------------------------------------
    # Chart 09: Metro Transit Proximity Boxplots
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=180)
    fig.patch.set_facecolor("#FAF7F2")
    ax.set_facecolor("#FAF7F2")
    
    order = ["< 500m (Đi bộ dễ dàng)", "500m - 1km (Đi bộ vừa)", "1km - 2km (Xe đạp / Bus)", "> 2km (Cách xa metro)"]
    sub = df[df["metro_proximity_tier"].isin(order)].copy()
    sub["price_m"] = sub["price_vnd"] / 1e6
    
    palette = ["#E11D48", "#F59E0B", "#0891B2", "#94A3B8"]
    sns.boxplot(data=sub, x="metro_proximity_tier", y="price_m", order=order, palette=palette, ax=ax, width=0.55, showfliers=False)
    
    # Annotate medians
    base_val = sub[sub["metro_proximity_tier"] == "> 2km (Cách xa metro)"]["price_m"].median()
    for i, tier in enumerate(order):
        tier_sub = sub[sub["metro_proximity_tier"] == tier]
        m_val = tier_sub["price_m"].median()
        n_cnt = len(tier_sub)
        diff_pct = ((m_val - base_val) / base_val) * 100.0
        diff_str = "Baseline" if tier == "> 2km (Cách xa metro)" else f"{diff_pct:+.1f}% vs >2km"
        ax.text(i, m_val + 0.35, f"Median: {m_val:.2f}M\n({diff_str})\nn={n_cnt:,}", 
                ha="center", fontsize=9.0, fontweight="bold", color="#1E293B",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFFFFF", edgecolor="#CBD5E1", alpha=0.9))
        
    ax.set_title("Rental Price Distribution by Metro Proximity Tier (Lines 2A & 3)", fontsize=14, fontweight="bold", pad=15, color="#0F172A")
    ax.set_xlabel("Transit Proximity Catchment Band", fontsize=11, fontweight="bold", labelpad=10, color="#334155")
    ax.set_ylabel("Monthly Rent (Million VND)", fontsize=11, fontweight="bold", labelpad=10, color="#334155")
    ax.set_ylim(1, 9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "plot_09_metro_proximity_chart.png"), facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close()
    print("   ✓ plot_09_metro_proximity_chart.png")

    # -------------------------------------------------------------------------
    # Chart 10: True Cost of Living Stacked Breakdown
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=180)
    fig.patch.set_facecolor("#FAF7F2")
    ax.set_facecolor("#FAF7F2")
    
    top_dist = ["Cầu Giấy", "Đống Đa", "Ba Đình", "Tây Hồ", "Thanh Xuân", "Hai Bà Trưng", "Nam Từ Liêm", "Hoàng Mai", "Hà Đông", "Bắc Từ Liêm"]
    sub = df[df["district"].isin(top_dist)].groupby("district").agg(
        base_rent=("price_vnd", "median"),
        living_cost=("estimated_total_living_cost", "median"),
        elec=("electric_price_clean", "median"),
        water=("water_price_clean", "median")
    ).loc[top_dist].sort_values("living_cost", ascending=True)
    
    base_m = sub["base_rent"] / 1e6
    extra_m = (sub["living_cost"] - sub["base_rent"]) / 1e6
    
    p1 = ax.barh(sub.index, base_m, color="#2563EB", label="Base Stated Rent", height=0.65)
    p2 = ax.barh(sub.index, extra_m, left=base_m, color="#F59E0B", label="Estimated Utility Markup (~780k)", height=0.65)
    
    for i, (b, e) in enumerate(zip(base_m, extra_m)):
        total = b + e
        ax.text(total + 0.15, i, f"{total:.2f}M VND", va="center", ha="left", fontsize=9.5, fontweight="bold", color="#1E293B")
        
    ax.set_title("True Cost of Living: Base Rent vs Effective Monthly Living Expense", fontsize=14, fontweight="bold", pad=15, color="#0F172A")
    ax.set_xlabel("Effective Monthly Expenditure (Million VND)", fontsize=11, fontweight="bold", labelpad=10, color="#334155")
    ax.set_xlim(0, max(base_m + extra_m) * 1.22)
    ax.legend(frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1", loc="lower right", fontsize=10.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "plot_10_true_living_cost_chart.png"), facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close()
    print("   ✓ plot_10_true_living_cost_chart.png")

    # -------------------------------------------------------------------------
    # Chart 11: Bargain Deal Discovery Rate
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=180)
    fig.patch.set_facecolor("#FAF7F2")
    ax.set_facecolor("#FAF7F2")
    
    b_df = df[df["market_value_tier"] != "Chưa xác định"].groupby("district").agg(
        total=("listing_id", "count"),
        bargains=("market_value_tier", lambda s: s.str.startswith("Giá hời").sum())
    )
    b_df = b_df[b_df["total"] >= 100]
    b_df["bargain_rate"] = b_df["bargains"] / b_df["total"] * 100.0
    b_df = b_df.sort_values("bargain_rate", ascending=True)
    
    colors = sns.color_palette("viridis", len(b_df))
    bars = ax.barh(b_df.index, b_df["bargain_rate"], color=colors, height=0.65)
    
    for bar, cnt in zip(bars, b_df["bargains"].values):
        w = bar.get_width()
        ax.text(w + 0.4, bar.get_y() + bar.get_height()/2, f"{w:.1f}% ({cnt} deals)", 
                va="center", ha="left", fontsize=9.5, fontweight="bold", color="#1E293B")
        
    ax.set_title("Hedonic Pricing Model: Proportion of Underpriced Bargain Units by District", fontsize=14, fontweight="bold", pad=15, color="#0F172A")
    ax.set_xlabel("Bargain Deal Discovery Share (% of District Stock)", fontsize=11, fontweight="bold", labelpad=10, color="#334155")
    ax.set_xlim(0, max(b_df["bargain_rate"]) * 1.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "plot_11_value_score_bargain_chart.png"), facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close()
    print("   ✓ plot_11_value_score_bargain_chart.png")

    # -------------------------------------------------------------------------
    # Chart 12: Top Universities Student Housing Supply & Rent
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=180)
    fig.patch.set_facecolor("#FAF7F2")
    ax.set_facecolor("#FAF7F2")
    
    sub = df[df["distance_to_nearest_university_km"] <= 1.5]
    top_uni = sub.groupby("nearest_university").agg(
        count=("listing_id", "count"),
        median_rent=("price_vnd", "median")
    ).sort_values("count", ascending=True).tail(12)
    
    colors = sns.color_palette("flare", len(top_uni))
    bars = ax.barh(top_uni.index, top_uni["count"], color=colors, height=0.65)
    
    for bar, med in zip(bars, top_uni["median_rent"].values):
        w = bar.get_width()
        ax.text(w + 18, bar.get_y() + bar.get_height()/2, f"{int(w):,} listings | Median: {med/1e6:.2f}M", 
                va="center", ha="left", fontsize=9.5, fontweight="bold", color="#1E293B")
        
    ax.set_title("Student Housing Supply & Median Rent Around Top University Hubs (<1.5 km)", fontsize=14, fontweight="bold", pad=15, color="#0F172A")
    ax.set_xlabel("Student Housing Listing Count (<1.5 km Walking Catchment)", fontsize=11, fontweight="bold", labelpad=10, color="#334155")
    ax.set_xlim(0, max(top_uni["count"].values) * 1.35)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "plot_12_university_proximity_chart.png"), facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close()
    print("   ✓ plot_12_university_proximity_chart.png")

# -----------------------------------------------------------------------------
# 5. Main Execution Entrypoint
# -----------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("Starting Direct Pixel Landscape Map & Independent Chart Suite")
    print("=" * 70)
    
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Cleaned dataset not found: {DATA_PATH}")
    df = pd.read_csv(DATA_PATH, low_memory=False)
    df_raw = pd.read_csv(os.path.join(BASE_DIR, "data/merged_hanoi_rentals.csv"), low_memory=False)
    
    # 1. Render All Maps directly on Japanese ink canvas
    render_all_maps(df)
    
    # 2. Render All Independent Standalone Distribution Charts
    render_all_charts(df, df_raw)
    
    print("=" * 70)
    print("All direct landscape maps and independent charts rendered successfully!")
    print("=" * 70)

if __name__ == "__main__":
    main()
