#!/usr/bin/env python3
"""
generate_proximity_factor_plots.py
===================================
Two analysis plots for Hanoi rental dataset:

  Plot 10 – Proximity Price Comparison
    Strip + box + mean-line chart comparing median rent for:
      · Metro proximity tiers
      · University proximity tiers
      · District-level average (baseline reference band)

  Plot 11 – Rent Price Factor Importance
    Horizontal bar chart of standardised OLS coefficients showing
    which features (area, location, metro, uni, amenities, …)
    explain the most variance in rent price.

Outputs (figures/):
    plot_10_proximity_price_comparison.png
    plot_11_rent_factor_importance.png
"""

import os
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

warnings.filterwarnings("ignore")
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR    = "/home/totallynotminh/Documents/FunDS"
DATA_PATH   = os.path.join(BASE_DIR, "data", "unified_hanoi_rentals.csv")
FIG_DIR     = os.path.join(BASE_DIR, "figures")
os.makedirs(FIG_DIR, exist_ok=True)

# ── Palette / style ──────────────────────────────────────────────────────────
PALETTE = {
    "metro"  : "#4E79A7",
    "uni"    : "#F28E2B",
    "area"   : "#59A14F",
    "bg"     : "#FAFAF8",
    "grid"   : "#E5E5E0",
    "text"   : "#2C2C2C",
    "accent" : "#E15759",
}

plt.rcParams.update({
    "font.family"     : "DejaVu Sans",
    "axes.facecolor"  : PALETTE["bg"],
    "figure.facecolor": PALETTE["bg"],
    "axes.edgecolor"  : PALETTE["grid"],
    "grid.color"      : PALETTE["grid"],
    "grid.linewidth"  : 0.6,
    "text.color"      : PALETTE["text"],
    "axes.labelcolor" : PALETTE["text"],
    "xtick.color"     : PALETTE["text"],
    "ytick.color"     : PALETTE["text"],
})

# ── Load & basic clean ───────────────────────────────────────────────────────
df = pd.read_csv(DATA_PATH)

# Keep rows with valid price and coordinates
df = df[df["price_vnd"].notna() & (df["price_vnd"] > 0)]
df = df[df["latitude"].notna() & df["longitude"].notna()]

# Remove extreme outliers (IQR × 3)
q1, q3 = df["price_vnd"].quantile(0.01), df["price_vnd"].quantile(0.99)
df = df[(df["price_vnd"] >= q1) & (df["price_vnd"] <= q3)]

price_M = df["price_vnd"] / 1_000_000   # price in million VND (display)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PLOT 10 — Proximity Price Comparison                                   ║
# ╚══════════════════════════════════════════════════════════════════════════╝

TIER_ORDER_METRO = [
    "< 500m (Đi bộ dễ dàng)",
    "500m - 1km (Đi bộ vừa)",
    "1km - 2km (Xe đạp / Bus)",
    "> 2km (Cách xa metro)",
]
TIER_ORDER_UNI = [
    "< 500m (Đi bộ dễ dàng)",
    "500m - 1km (Đi bộ vừa)",
    "1km - 2km (Xe đạp / Bus)",
    "> 2km (Khu vực ngoài SV)",
]

TIER_LABELS_METRO = ["<500 m", "500m–1km", "1–2 km", ">2 km"]
TIER_LABELS_UNI   = ["<500 m", "500m–1km", "1–2 km", ">2 km"]

df_metro = df[df["metro_proximity_tier"].isin(TIER_ORDER_METRO)].copy()
df_metro["tier_label"] = pd.Categorical(
    df_metro["metro_proximity_tier"].map(dict(zip(TIER_ORDER_METRO, TIER_LABELS_METRO))),
    categories=TIER_LABELS_METRO, ordered=True
)

df_uni = df[df["university_proximity_tier"].isin(TIER_ORDER_UNI)].copy()
df_uni["tier_label"] = pd.Categorical(
    df_uni["university_proximity_tier"].map(dict(zip(TIER_ORDER_UNI, TIER_LABELS_UNI))),
    categories=TIER_LABELS_UNI, ordered=True
)

# District medians for area baseline band
district_medians = (df.groupby("district")["price_vnd"].median() / 1_000_000)
area_low  = district_medians.quantile(0.25)
area_med  = district_medians.median()
area_high = district_medians.quantile(0.75)

# ── Aggregate stats ──────────────────────────────────────────────────────────
def tier_stats(data, col="tier_label"):
    g = data.groupby(col, observed=True)["price_vnd"]
    return pd.DataFrame({
        "median": g.median() / 1_000_000,
        "q25"   : g.quantile(0.25) / 1_000_000,
        "q75"   : g.quantile(0.75) / 1_000_000,
        "n"     : g.count(),
    })

metro_stats = tier_stats(df_metro)
uni_stats   = tier_stats(df_uni)

fig, axes = plt.subplots(1, 2, figsize=(15, 6.5), sharey=False)
fig.patch.set_facecolor(PALETTE["bg"])

def draw_proximity_panel(ax, stats, color, xlabel, title):
    x = np.arange(len(stats))
    bars = ax.bar(x, stats["median"], width=0.55, color=color, alpha=0.85,
                  zorder=3, edgecolor="white", linewidth=0.8)
    # IQR error caps
    err_low  = stats["median"] - stats["q25"]
    err_high = stats["q75"]    - stats["median"]
    ax.errorbar(x, stats["median"],
                yerr=[err_low, err_high],
                fmt="none", color="#333333", capsize=6, linewidth=1.4, zorder=4)
    # Area baseline band
    ax.axhspan(area_low, area_high, color=PALETTE["area"], alpha=0.12, zorder=1)
    ax.axhline(area_med, color=PALETTE["area"], linewidth=1.6,
               linestyle="--", zorder=2, label=f"District median avg\n({area_med:.1f}M VND)")
    # Value labels
    for xi, (med, n) in enumerate(zip(stats["median"], stats["n"])):
        ax.text(xi, med + 0.25, f"{med:.1f}M\n(n={n:,})",
                ha="center", va="bottom", fontsize=8.5,
                color=PALETTE["text"], fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(stats.index, fontsize=10)
    ax.set_xlabel(xlabel, fontsize=11, labelpad=6)
    ax.set_ylabel("Median Rent Price (Million VND / month)", fontsize=10)
    ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
    ax.yaxis.grid(True, linestyle="--", alpha=0.7)
    ax.set_axisbelow(True)
    ax.legend(fontsize=9, loc="upper right")
    ax.spines[["top","right"]].set_visible(False)

draw_proximity_panel(
    axes[0], metro_stats, PALETTE["metro"],
    "Distance to Nearest Metro Station",
    "Metro Proximity vs Median Rent"
)
draw_proximity_panel(
    axes[1], uni_stats, PALETTE["uni"],
    "Distance to Nearest University",
    "University Proximity vs Median Rent"
)

# Shared legend for the shaded band
band_patch = mpatches.Patch(color=PALETTE["area"], alpha=0.25,
                             label="Inter-quartile range\nof district medians")
fig.legend(handles=[band_patch], loc="lower center", ncol=1,
           fontsize=9, bbox_to_anchor=(0.5, -0.02))

fig.suptitle(
    "How Proximity to Metro & University Affects Hanoi Rental Prices\n"
    "(shaded band = IQR of district-level median prices as area baseline)",
    fontsize=14, fontweight="bold", y=1.01
)
fig.tight_layout()
out10 = os.path.join(FIG_DIR, "plot_10_proximity_price_comparison.png")
fig.savefig(out10, dpi=150, bbox_inches="tight", facecolor=PALETTE["bg"])
plt.close(fig)
print(f"[✓] Saved {out10}")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PLOT 11 — Spearman Correlation heatmap vs rent price                   ║
# ╚══════════════════════════════════════════════════════════════════════════╝

from scipy.stats import spearmanr

df_clean = df[["price_vnd", "area_m2", "distance_to_center_km",
               "distance_to_nearest_metro_km", "distance_to_nearest_university_km",
               "house_type", "district"]].dropna(subset=["price_vnd"])

# Target-encode categoricals: replace each category with its mean price_vnd
df_clean = df_clean.copy()
df_clean["house_type_enc"] = df_clean.groupby("house_type")["price_vnd"].transform("mean")
df_clean["district_enc"]   = df_clean.groupby("district")["price_vnd"].transform("mean")

FEATURES = {
    "area_m2"                          : "Area (m²)",
    "distance_to_center_km"            : "Distance to City Center",
    "distance_to_nearest_metro_km"     : "Distance to Metro",
    "distance_to_nearest_university_km": "Distance to University",
    "house_type_enc"                   : "House Type",
    "district_enc"                     : "District",
}

rows = []
for col, label in FEATURES.items():
    sub = df_clean[[col, "price_vnd"]].dropna()
    r, p = spearmanr(sub[col], sub["price_vnd"])
    rows.append({"Feature": label, "ρ": round(r, 3)})

corr_df = pd.DataFrame(rows).sort_values("ρ")
heat_data = corr_df.set_index("Feature")[["ρ"]]

fig, ax = plt.subplots(figsize=(4.5, len(corr_df) * 0.75 + 1.5))
fig.patch.set_facecolor(PALETTE["bg"])

sns.heatmap(
    heat_data,
    ax=ax,
    annot=True,
    fmt=".3f",
    cmap="RdYlGn",
    center=0,
    vmin=-1, vmax=1,
    linewidths=1.2,
    linecolor=PALETTE["bg"],
    annot_kws={"size": 12, "weight": "bold"},
    cbar_kws={"label": "Spearman ρ", "shrink": 0.7},
)

ax.set_xlabel("")
ax.set_ylabel("")
ax.set_title(
    "Spearman Correlation with\nRent Price (price_vnd)",
    fontsize=13, fontweight="bold", pad=12, color=PALETTE["text"]
)
ax.tick_params(axis="x", bottom=False, labelbottom=False)
ax.tick_params(axis="y", labelsize=11)
plt.setp(ax.get_yticklabels(), rotation=0)

fig.tight_layout()
out11 = os.path.join(FIG_DIR, "plot_11_rent_factor_importance.png")
fig.savefig(out11, dpi=150, bbox_inches="tight", facecolor=PALETTE["bg"])
plt.close(fig)
print(f"[✓] Saved {out11}")

print("\nDone. Both plots generated successfully.")

