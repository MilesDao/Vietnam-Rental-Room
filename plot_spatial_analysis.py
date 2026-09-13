"""
plot_spatial_analysis.py - Comprehensive Geographical & Spatial Analysis Dashboard for Hanoi Rental Housing Market

Generates a unified, publication-quality 5-panel spatial dashboard:
1. Plot 1: Spatial Point Density & Cluster Hotspots (2D KDE Contour Heatmap with explicitly labeled Universities & Lakes)
2. Plot 2: Spatial Price Distribution Map (Lat/Lon Scatter with Landmark Legend: Triangles = Universities, Circles = City Center)
3. Plot 3: Hexagonal Spatial Binning (H3 Proxy Hexbin Density & Median Price)
4. Plot 4: District-level Listing Volume & Supply Market Share (Top 10 Districts)
5. Plot 5: Rental Price Distribution Across Districts (Boxplot + Median Markers)
"""

import os
import sys
from pathlib import Path

# Configure local writable Matplotlib cache directory
WORKSPACE_DIR = Path(__file__).resolve().parent
os.environ["MPLCONFIGDIR"] = str(WORKSPACE_DIR / ".mplconfig")
(WORKSPACE_DIR / ".mplconfig").mkdir(parents=True, exist_ok=True)

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for headless rendering
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.colors import Normalize
import seaborn as sns
from scipy.stats import gaussian_kde

# Canonical Hanoi Districts Whitelist
HANOI_CANONICAL_DISTRICTS = [
    "Ba Đình", "Bắc Từ Liêm", "Cầu Giấy", "Đống Đa", "Hà Đông", "Hai Bà Trưng",
    "Hoàn Kiếm", "Hoàng Mai", "Long Biên", "Nam Từ Liêm", "Tây Hồ", "Thanh Xuân",
    "Sơn Tây", "Ba Vì", "Chương Mỹ", "Đan Phượng", "Đông Anh", "Gia Lâm",
    "Hoài Đức", "Mê Linh", "Mỹ Đức", "Phú Xuyên", "Phúc Thọ", "Quốc Oai",
    "Sóc Sơn", "Thạch Thất", "Thanh Oai", "Thanh Trì", "Thường Tín", "Ứng Hòa"
]

# ==============================================================================
# 1. LOAD & CLEAN DATASET
# ==============================================================================

def load_and_preprocess_data(csv_path: Path) -> pd.DataFrame:
    print(f"📂 Loading dataset from: {csv_path}...")
    df = pd.read_csv(csv_path, low_memory=False)
    print(f"   Raw records: {len(df):,}")

    # Convert numeric fields
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["price_vnd"] = pd.to_numeric(df["price_vnd"], errors="coerce")
    df["area_m2"] = pd.to_numeric(df["area_m2"], errors="coerce")

    # Filter valid Hanoi coordinates
    # Hanoi bounding box: Lat [20.7, 21.4], Lon [105.6, 106.1]
    valid_coords = (
        (df["latitude"].between(20.7, 21.4)) &
        (df["longitude"].between(105.6, 106.1))
    )
    df = df[valid_coords].copy()

    # Filter reasonable rental prices and areas (removing extreme outliers)
    valid_values = (
        (df["price_vnd"] >= 500_000) & (df["price_vnd"] <= 25_000_000) &
        (df["area_m2"] >= 8) & (df["area_m2"] <= 120)
    )
    df = df[valid_values].copy()

    # Feature Engineering
    df["price_million"] = df["price_vnd"] / 1_000_000.0
    df["price_per_m2_k"] = (df["price_vnd"] / df["area_m2"]) / 1_000.0  # in thousand VND/m2

    # Clean district names and match against canonical Hanoi districts
    df["district_clean"] = df["district"].astype(str).str.replace(r"^(Quận|Huyện|Thị xã)\s+", "", regex=True).str.strip()
    
    canonical_map = {d.lower(): d for d in HANOI_CANONICAL_DISTRICTS}
    df["district_hanoi"] = df["district_clean"].apply(lambda x: canonical_map.get(x.lower()))
    df = df[df["district_hanoi"].notnull()].copy()
    df["district"] = df["district_hanoi"]

    print(f"   Cleaned records ready for spatial analysis: {len(df):,}")
    return df


# ==============================================================================
# 2. GENERATE UNIFIED 5-PANEL SPATIAL DASHBOARD
# ==============================================================================

def create_spatial_dashboard_5_plots(df: pd.DataFrame, output_path: Path):
    print("\n🎨 Rendering 5 Core Geographical & Spatial Analysis Dashboard...")
    
    # Visual Theme Setup
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig = plt.figure(figsize=(24, 15), dpi=300)
    fig.patch.set_facecolor("#FAFAFA")
    
    # Main Dashboard Title
    fig.suptitle(
        "HANOI RENTAL HOUSING MARKET — 5 CORE GEOGRAPHICAL & SPATIAL PLOTS\n"
        f"District Distribution, Listing Density, H3 Hexagonal Binning & Spatial Price Variations ({len(df):,} Clean Properties)",
        fontsize=18,
        fontweight="bold",
        color="#1E293B",
        y=0.98
    )

    # 6-column GridSpec for balanced 3-top / 2-bottom layout
    gs = gridspec.GridSpec(2, 6, figure=fig, hspace=0.28, wspace=0.45)

    # Detailed landmark reference points in Hanoi for Plot 1
    landmarks_plot1 = [
        {"name": "Nhổn / ĐH Công Nghiệp", "lat": 21.0550, "lon": 105.7350, "text_pos": (105.708, 21.080)},
        {"name": "ĐH Quốc Gia Hà Nội\n(Xuân Thủy - Cầu Giấy)", "lat": 21.0378, "lon": 105.7814, "text_pos": (105.708, 21.045)},
        {"name": "Keangnam 72\n(Mỹ Đình - Mễ Trì)", "lat": 21.0169, "lon": 105.7839, "text_pos": (105.708, 21.010)},
        {"name": "Văn Quán - Hà Đông", "lat": 20.9650, "lon": 105.7700, "text_pos": (105.710, 20.945)},
        {"name": "Chùa Láng - Đường Láng", "lat": 21.0230, "lon": 105.8050, "text_pos": (105.772, 21.082), "is_highlight": True},
        {"name": "Hồ Tây", "lat": 21.0583, "lon": 105.8250, "text_pos": (105.845, 21.082)},
        {"name": "Hồ Hoàn Kiếm\n(Phố Cổ)", "lat": 21.0288, "lon": 105.8522, "text_pos": (105.862, 21.045)},
        {"name": "ĐH Bách Khoa Hà Nội\n(Bách - Kinh - Xây)", "lat": 21.0044, "lon": 105.8437, "text_pos": (105.856, 20.978)},
    ]

    # Focus map boundary (Hanoi Urban Core)
    xmin, xmax = 105.70, 105.92
    ymin, ymax = 20.93, 21.10

    # -------------------------------------------------------------------------
    # PLOT 1 (ROW 0, COLS 0-1): SPATIAL POINT DENSITY & KDE CLUSTER HOTSPOTS
    # -------------------------------------------------------------------------
    ax1 = fig.add_subplot(gs[0, 0:2])
    ax1.set_facecolor("#FFFFFF")
    
    x = df["longitude"].values
    y = df["latitude"].values
    xy = np.vstack([x, y])
    kde = gaussian_kde(xy)
    
    xx, yy = np.mgrid[xmin:xmax:120j, ymin:ymax:120j]
    positions = np.vstack([xx.ravel(), yy.ravel()])
    z = np.reshape(kde(positions).T, xx.shape)
    
    contour = ax1.contourf(xx, yy, z, levels=15, cmap="YlOrRd", alpha=0.75)
    ax1.scatter(x, y, c="#0F172A", s=3.5, alpha=0.25, rasterized=True)
    
    # Direct arrow pointers to black dot clusters / hotspots (NO artificial geometric shape markers)
    for lm in landmarks_plot1:
        lon, lat = lm["lon"], lm["lat"]
        tx, ty = lm["text_pos"]
        is_hl = lm.get("is_highlight", False)
        
        edge_col = "#DC2626" if is_hl else "#334155"
        face_col = "#FEF2F2" if is_hl else "#FFFFFF"
        text_col = "#991B1B" if is_hl else "#0F172A"
        arrow_col = "#DC2626" if is_hl else "#0F172A"
        lw = 1.4 if is_hl else 1.0
        
        ax1.annotate(
            lm["name"],
            xy=(lon, lat),
            xytext=(tx, ty),
            fontsize=7.8,
            fontweight="bold",
            color=text_col,
            bbox=dict(boxstyle="round,pad=0.25", facecolor=face_col, edgecolor=edge_col, alpha=0.95, lw=lw),
            arrowprops=dict(arrowstyle="-|>", color=arrow_col, lw=lw, shrinkA=2, shrinkB=0),
            zorder=10 if is_hl else 6
        )
        
    ax1.set_xlim(xmin, xmax)
    ax1.set_ylim(ymin, ymax)
    ax1.set_title("Plot 1: Listing Density & Cluster Hotspots (KDE Heatmap)", fontsize=12, fontweight="bold", pad=10)
    ax1.set_xlabel("Longitude (°E)", fontsize=10)
    ax1.set_ylabel("Latitude (°N)", fontsize=10)
    cbar1 = fig.colorbar(contour, ax=ax1, fraction=0.046, pad=0.04)
    cbar1.set_label("Spatial Density Index", fontsize=9)

    # -------------------------------------------------------------------------
    # PLOT 2 (ROW 0, COLS 2-3): SPATIAL PRICE DISTRIBUTION MAP
    # -------------------------------------------------------------------------
    ax2 = fig.add_subplot(gs[0, 2:4])
    ax2.set_facecolor("#FFFFFF")
    
    norm = Normalize(vmin=2.0, vmax=10.0)
    scatter = ax2.scatter(
        df["longitude"],
        df["latitude"],
        c=df["price_million"],
        cmap="Spectral_r",
        norm=norm,
        s=12,
        alpha=0.65,
        edgecolors="none",
        rasterized=True
    )
    
    # Landmark markers with clean single-symbol legend
    p_uni1 = ax2.plot(105.7814, 21.0378, marker="^", markersize=9, color="#1E293B", markeredgecolor="#FFFFFF", markeredgewidth=1.2, linestyle="None", label="Trường ĐH Trọng điểm (ĐHQG, ĐHBK)")
    p_uni2 = ax2.plot(105.8437, 21.0044, marker="^", markersize=9, color="#1E293B", markeredgecolor="#FFFFFF", markeredgewidth=1.2, linestyle="None")
    p_center = ax2.plot(105.8522, 21.0288, marker="o", markersize=8.5, color="#DC2626", markeredgecolor="#FFFFFF", markeredgewidth=1.2, linestyle="None", label="Trung tâm Hoàn Kiếm")

    # Annotate directly on map
    ax2.text(105.7814 - 0.035, 21.0378 + 0.005, "ĐHQG", fontsize=8.5, fontweight="bold", color="#1E293B", bbox=dict(boxstyle="round,pad=0.2", facecolor="#FFFFFF", alpha=0.85, edgecolor="#94A3B8"))
    ax2.text(105.8437 + 0.005, 21.0044 - 0.007, "ĐHBK", fontsize=8.5, fontweight="bold", color="#1E293B", bbox=dict(boxstyle="round,pad=0.2", facecolor="#FFFFFF", alpha=0.85, edgecolor="#94A3B8"))
    ax2.text(105.8522 + 0.005, 21.0288 + 0.004, "Hồ Gươm", fontsize=8.5, fontweight="bold", color="#DC2626", bbox=dict(boxstyle="round,pad=0.2", facecolor="#FFFFFF", alpha=0.85, edgecolor="#DC2626"))

    ax2.set_xlim(xmin, xmax)
    ax2.set_ylim(ymin, ymax)
    ax2.set_title("Plot 2: Spatial Price Distribution Map (Rental Price)", fontsize=12, fontweight="bold", pad=10)
    ax2.set_xlabel("Longitude (°E)", fontsize=10)
    ax2.set_ylabel("Latitude (°N)", fontsize=10)
    
    # Legend for symbols
    ax2.legend(loc="lower left", fontsize=8.5, framealpha=0.9, facecolor="#FFFFFF", edgecolor="#CBD5E1")
    
    cbar2 = fig.colorbar(scatter, ax=ax2, fraction=0.046, pad=0.04)
    cbar2.set_label("Monthly Rent (Million VND)", fontsize=9)

    # -------------------------------------------------------------------------
    # PLOT 3 (ROW 0, COLS 4-5): HEXAGONAL SPATIAL BINNING (H3 PROXY)
    # -------------------------------------------------------------------------
    ax3 = fig.add_subplot(gs[0, 4:6])
    ax3.set_facecolor("#FFFFFF")
    
    hex_norm = Normalize(vmin=2.0, vmax=7.5)
    hb = ax3.hexbin(
        df["longitude"],
        df["latitude"],
        C=df["price_million"],
        gridsize=26,
        reduce_C_function=np.median,
        cmap="viridis",
        norm=hex_norm,
        mincnt=3,
        edgecolors="#FFFFFF",
        linewidths=0.3
    )
    
    # Landmark callouts on Plot 3 pointing directly into the hexagon cells (no artificial geometric markers)
    hex_landmarks = [
        {"name": "Hồ Tây\n(5.0-6.0M: Xanh lục)", "lat": 21.0583, "lon": 105.8250, "text_pos": (105.830, 21.085)},
        {"name": "Hồ Gươm\n(4.5-5.5M: Xanh ngọc)", "lat": 21.0288, "lon": 105.8522, "text_pos": (105.862, 21.045)},
        {"name": "ĐH Quốc Gia (Xuân Thủy)\n(4.5-5.2M: Xanh ngọc)", "lat": 21.0378, "lon": 105.7814, "text_pos": (105.710, 21.045)},
        {"name": "Keangnam / Mỹ Đình\n(5.0-6.5M: Xanh lục sáng)", "lat": 21.0169, "lon": 105.7839, "text_pos": (105.710, 21.008)},
        {"name": "ĐH Bách Khoa (Giải Phóng)\n(5.0-5.8M: Xanh lục sáng)", "lat": 21.0044, "lon": 105.8437, "text_pos": (105.855, 20.995)},
        {"name": "Nhổn (ĐH Công Nghiệp)\n(3.0-3.5M: Xanh tím)", "lat": 21.0550, "lon": 105.7350, "text_pos": (105.705, 21.085)},
        {"name": "Văn Quán - Hà Đông\n(3.0-3.5M: Xanh tím)", "lat": 20.9650, "lon": 105.7700, "text_pos": (105.710, 20.945)},
        {"name": "Bán đảo Linh Đàm\n(2.5-3.0M: Tím đậm)", "lat": 20.9650, "lon": 105.8300, "text_pos": (105.845, 20.945)},
    ]
    
    for lm in hex_landmarks:
        lon, lat = lm["lon"], lm["lat"]
        tx, ty = lm["text_pos"]
        
        ax3.annotate(
            lm["name"],
            xy=(lon, lat),
            xytext=(tx, ty),
            fontsize=7.8,
            fontweight="bold",
            color="#0F172A",
            bbox=dict(boxstyle="round,pad=0.22", facecolor="#FFFFFF", edgecolor="#334155", alpha=0.92, lw=0.7),
            arrowprops=dict(arrowstyle="-|>", color="#0F172A", lw=1.1, shrinkA=2, shrinkB=0),
            zorder=6
        )
    
    ax3.set_xlim(xmin, xmax)
    ax3.set_ylim(ymin, ymax)
    ax3.set_title("Plot 3: Hexagonal Spatial Binning (H3 Proxy Median Price)", fontsize=12, fontweight="bold", pad=10)
    ax3.set_xlabel("Longitude (°E)", fontsize=10)
    ax3.set_ylabel("Latitude (°N)", fontsize=10)
    cbar3 = fig.colorbar(hb, ax=ax3, fraction=0.046, pad=0.04)
    cbar3.set_label("Median Rent in Hexbin (Million VND)", fontsize=9)

    # -------------------------------------------------------------------------
    # PLOT 4 (ROW 1, COLS 0-2): DISTRICT-LEVEL LISTING VOLUME (SUPPLY SHARE)
    # -------------------------------------------------------------------------
    ax4 = fig.add_subplot(gs[1, 0:3])
    ax4.set_facecolor("#FFFFFF")
    
    top_districts = df["district"].value_counts().head(10)
    colors = sns.color_palette("Blues_r", len(top_districts))
    
    bars = ax4.barh(top_districts.index[::-1], top_districts.values[::-1], color=colors[::-1], edgecolor="#CBD5E1")
    for bar in bars:
        w = bar.get_width()
        pct = (w / len(df)) * 100
        ax4.text(w + 20, bar.get_y() + bar.get_height()/2, f"{w:,} ({pct:.1f}%)", va="center", fontsize=9.5, fontweight="semibold", color="#334155")
        
    ax4.set_title("Plot 4: District-level Listing Volume & Supply Share (Top 10 Districts)", fontsize=13, fontweight="bold", pad=10)
    ax4.set_xlabel("Total Available Listings", fontsize=11)
    ax4.set_xlim(0, top_districts.max() * 1.22)

    # -------------------------------------------------------------------------
    # PLOT 5 (ROW 1, COLS 3-5): RENTAL PRICE DISTRIBUTION BY DISTRICT (BOXPLOT)
    # -------------------------------------------------------------------------
    ax5 = fig.add_subplot(gs[1, 3:6])
    ax5.set_facecolor("#FFFFFF")
    
    top_district_names = top_districts.index.tolist()
    sub_df = df[df["district"].isin(top_district_names)].copy()
    
    median_order = sub_df.groupby("district")["price_million"].median().sort_values(ascending=False).index
    
    sns.boxplot(
        data=sub_df,
        y="district",
        x="price_million",
        order=median_order,
        hue="district",
        legend=False,
        palette="Spectral",
        showmeans=True,
        meanprops={"marker":"o", "markerfacecolor":"white", "markeredgecolor":"black", "markersize":"5"},
        fliersize=2,
        ax=ax5
    )
    
    ax5.set_title("Plot 5: Rental Price Distribution Across Districts (Boxplot & Median)", fontsize=13, fontweight="bold", pad=10)
    ax5.set_xlabel("Monthly Rent (Million VND)", fontsize=11)
    ax5.set_ylabel("")
    ax5.set_xlim(0, 25)

    # Export figure
    fig.savefig(output_path, dpi=300, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    print(f"✅ 5-Plot Dashboard successfully saved to: {output_path}")


# ==============================================================================
# 3. MAIN EXECUTION
# ==============================================================================

def main():
    csv_candidates = [
        WORKSPACE_DIR / "merged_hanoi_rentals.csv",
        WORKSPACE_DIR / "raw_phongtro123.csv",
        WORKSPACE_DIR / "phongtro123_cleaned.csv"
    ]
    
    target_csv = None
    for p in csv_candidates:
        if p.exists():
            target_csv = p
            break
            
    if not target_csv:
        print("❌ Error: No valid CSV dataset found in workspace.")
        sys.exit(1)
        
    df = load_and_preprocess_data(target_csv)
    
    output_png = WORKSPACE_DIR / "spatial_analysis_dashboard.png"
    create_spatial_dashboard_5_plots(df, output_png)
    
    print("\n" + "=" * 70)
    print("📊 TỔNG HỢP 5 PLOT CHÍNH TRONG DASHBOARD:")
    print("=" * 70)
    print("1. Plot 1: Listing Density & Cluster Hotspots (KDE Heatmap)")
    print("2. Plot 2: Spatial Price Distribution Map (Lat/Lon colored by Price)")
    print("3. Plot 3: Hexagonal Spatial Binning (H3 Proxy Median Price)")
    print("4. Plot 4: District Supply Share (Top 10 Districts Volume)")
    print("5. Plot 5: District Price Distribution (Boxplot with Median & Outliers)")
    print("=" * 70)


if __name__ == "__main__":
    main()
