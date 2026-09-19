#!/usr/bin/env python3
"""
generate_density_heatmap.py
============================
Generates plot_02_density_heatmap.png — a 2D KDE listing density heatmap
overlaid on a basemap-style coordinate grid, using the unified_hanoi_rentals.csv
dataset. Saves to figures/.
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.ndimage import gaussian_filter

os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"

BASE_DIR  = "/home/totallynotminh/Documents/FunDS"
DATA_PATH = os.path.join(BASE_DIR, "data", "unified_hanoi_rentals.csv")
FIG_DIR   = os.path.join(BASE_DIR, "figures")
OUT_PATH  = os.path.join(FIG_DIR, "plot_02_density_heatmap.png")

# ── Load & filter geocoded listings ──────────────────────────────────────────
df = pd.read_csv(DATA_PATH)
geo = df.dropna(subset=["latitude", "longitude"]).copy()
geo = geo[
    (geo["latitude"]  >= 20.53) & (geo["latitude"]  <= 21.39) &
    (geo["longitude"] >= 105.28) & (geo["longitude"] <= 106.03)
]

lons = geo["longitude"].values
lats = geo["latitude"].values

# ── 2D histogram density (fast) ───────────────────────────────────────────────
GRID_RES = 400
lon_min, lon_max = lons.min() - 0.01, lons.max() + 0.01
lat_min, lat_max = lats.min() - 0.01, lats.max() + 0.01

H, xedges, yedges = np.histogram2d(
    lons, lats,
    bins=GRID_RES,
    range=[[lon_min, lon_max], [lat_min, lat_max]]
)
# Smooth with Gaussian filter (sigma controls spread, ~equivalent to KDE bandwidth)
Zi = gaussian_filter(H.T, sigma=6)

Xi = (xedges[:-1] + xedges[1:]) / 2
Yi = (yedges[:-1] + yedges[1:]) / 2
Xi, Yi = np.meshgrid(Xi, Yi)

# ── District label positions (major districts only) ───────────────────────────
DISTRICT_LABELS = {
    "Hoàn Kiếm"   : (105.852, 21.028),
    "Ba Đình"      : (105.837, 21.038),
    "Đống Đa"      : (105.840, 21.022),
    "Hai Bà Trưng" : (105.862, 21.007),
    "Thanh Xuân"   : (105.813, 20.994),
    "Cầu Giấy"     : (105.793, 21.033),
    "Tây Hồ"       : (105.830, 21.060),
    "Hoàng Mai"    : (105.868, 20.973),
    "Nam Từ Liêm"  : (105.766, 21.013),
    "Bắc Từ Liêm"  : (105.773, 21.053),
    "Hà Đông"      : (105.776, 20.968),
    "Long Biên"    : (105.897, 21.032),
}

# ── Plot ──────────────────────────────────────────────────────────────────────
BG = "#0D1117"
fig, ax = plt.subplots(figsize=(12, 10), dpi=150)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

# Heatmap
cmap = matplotlib.colormaps["inferno"]
img = ax.pcolormesh(Xi, Yi, Zi, cmap=cmap, shading="gouraud", zorder=1)

# Contour lines for structure
levels = np.percentile(Zi[Zi > 0], [50, 75, 90, 97])
ax.contour(Xi, Yi, Zi, levels=levels, colors="white", linewidths=0.4,
           alpha=0.3, zorder=2)

# Raw scatter (very faint) for texture
ax.scatter(lons, lats, s=0.4, c="white", alpha=0.06, zorder=3, linewidths=0)

# District labels
for name, (lon, lat) in DISTRICT_LABELS.items():
    ax.text(lon, lat, name, fontsize=7.5, color="white", alpha=0.80,
            ha="center", va="center", zorder=4,
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", fc="black", alpha=0.35, ec="none"))

# Colorbar
cbar = fig.colorbar(img, ax=ax, fraction=0.025, pad=0.02)
cbar.set_label("Listing Density (KDE)", color="white", fontsize=10)
cbar.ax.yaxis.set_tick_params(color="white")
plt.setp(cbar.ax.yaxis.get_ticklabels(), color="white")
cbar.outline.set_edgecolor("white")

# Axes styling
ax.set_xlim(lon_min, lon_max)
ax.set_ylim(lat_min, lat_max)
ax.set_xlabel("Longitude", fontsize=10, color="white")
ax.set_ylabel("Latitude",  fontsize=10, color="white")
ax.tick_params(colors="white", labelsize=8)
for spine in ax.spines.values():
    spine.set_edgecolor("#333333")

ax.set_title(
    f"Hanoi Rental Listing Density Heatmap\n"
    f"2D Kernel Density Estimation — {len(geo):,} geocoded listings",
    fontsize=14, fontweight="bold", color="white", pad=14
)

# Stats annotation
ax.text(0.01, 0.01,
        f"n = {len(geo):,} listings  |  KDE bandwidth = 0.035°  |  Source: unified_hanoi_rentals.csv",
        transform=ax.transAxes, fontsize=7, color="#888888",
        va="bottom", ha="left")

fig.tight_layout()
fig.savefig(OUT_PATH, dpi=150, bbox_inches="tight", facecolor=BG)
plt.close(fig)
print(f"[✓] Saved {OUT_PATH}")
