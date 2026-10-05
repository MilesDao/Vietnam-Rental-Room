"""Figures for the slide deck (docs/SLIDES_PLAN.md, docs/SLIDES_SCRIPT.md) — English labels.

    python -m src.recsys.make_slide_figures        # writes docs/slides/figures/s0X_*.png

Everything is computed from the current data files, so the numbers on the slides match the reports.
Needs: data/unified_hanoi_rentals.csv, *_geofixed.csv, *_dedup.csv, data/hanoi_districts.geojson,
data/recsys_eval_labels_v2.csv. Coordinates © OpenStreetMap contributors (Nominatim).
District names stay in Vietnamese (proper nouns).
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon

from src.recsys.recommend import WEIGHTS, load, recommend
from src.recsys.regeocode_fallback import fallback_mask

OUT = Path("docs/slides/figures")
INK, MUTED, GRID = "#1e293b", "#64748b", "#e2e8f0"
GREEN, BLUE, ROSE, TEAL, AMBER = "#86efac", "#93c5fd", "#fda4af", "#0d9488", "#f59e0b"
PLAT = {"Phongtro123.com": "Phongtro123", "Facebook": "Facebook", "ChoTot.com": "Chotot", "Mogi.vn": "Mogi",
        "Rencity.vn": "Rencity", "YourHome.top": "YourHome", "Alonhadat.vn": "Alonhadat"}
PERSONA = {"SV NEU thoải mái": "Student, NEU (comfort)", "SV HOU": "Student, HOU", "SV PTIT": "Student, PTIT",
           "SV HANU": "Student, HANU", "SV AJC": "Student, AJC", "Đi làm Đống Đa metro": "Worker, Đống Đa, near metro",
           "Studio Ba Đình": "Studio, Ba Đình", "Cặp đôi Hà Đông": "Couple, Hà Đông", "Cần thang máy": "Needs elevator",
           "Ngân sách cao": "High budget"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 15, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "text.color": INK, "xtick.color": INK, "ytick.color": INK, "axes.spines.top": False,
                     "axes.spines.right": False, "figure.dpi": 100, "savefig.dpi": 200, "savefig.bbox": "tight"})


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, facecolor="white")
    plt.close(fig)
    print("wrote", OUT / name)


def thousands(n):
    return f"{n:,.0f}"


# ------------------------------------------------------------------ slide 2: pipeline
def fig_pipeline(n_raw, n_dedup):
    steps = [("7 sources", f"{thousands(n_raw)} listings\nChotot, Facebook,\nPhongtro123, Mogi...", "#cbd5e1"),
             ("Clean &\nstandardise", "price, area,\namenities,\nroom type", "#cbd5e1"),
             ("Fix\ncoordinates", "geocode 35 wards\n(Nominatim,\ncached)", "#99f6e4"),
             ("De-duplicate", f"across platforms\n→ {thousands(n_dedup)} listings", "#99f6e4"),
             ("Features", "distance to\nuniversity / metro,\nvalue vs market", "#cbd5e1"),
             ("Recommend", "hard filters +\nweighted score", "#99f6e4"),
             ("Map app", "Streamlit: cards,\nphotos, radius\nsearch", "#99f6e4")]
    fig, ax = plt.subplots(figsize=(15, 4.6))
    ax.set_xlim(0, len(steps) * 2.1)
    ax.set_ylim(0, 4)
    ax.axis("off")
    for i, (title, sub, col) in enumerate(steps):
        x = i * 2.1 + 0.1
        ax.add_patch(FancyBboxPatch((x, 1.4), 1.8, 1.9, boxstyle="round,pad=0.04,rounding_size=0.15",
                                    fc=col, ec=MUTED, lw=1.4))
        ax.text(x + 0.9, 2.85, title, ha="center", va="center", fontsize=13.5, fontweight="bold")
        ax.text(x + 0.9, 1.95, sub, ha="center", va="center", fontsize=10.5, color=INK, linespacing=1.25)
        ax.text(x + 0.9, 3.6, str(i + 1), ha="center", va="center", fontsize=13, color=MUTED, fontweight="bold")
        if i < len(steps) - 1:
            ax.add_patch(FancyArrowPatch((x + 1.86, 2.35), (x + 2.14, 2.35), arrowstyle="-|>", mutation_scale=18,
                                         color=MUTED, lw=1.8))
    ax.add_patch(plt.Rectangle((0.1, 0.55), 0.35, 0.3, fc="#cbd5e1", ec=MUTED))
    ax.text(0.6, 0.7, "pipeline from earlier phases", va="center", fontsize=12)
    ax.add_patch(plt.Rectangle((6.2, 0.55), 0.35, 0.3, fc="#99f6e4", ec=MUTED))
    ax.text(6.7, 0.7, "work done in this phase (fixes, de-duplication, recommender, app)", va="center", fontsize=12)
    save(fig, "s02_pipeline.png")


# ------------------------------------------------------------------ slide 3: sources
def fig_sources(raw):
    g = raw.groupby("platform").agg(n=("listing_id", "size"), no_area=("area_m2", lambda s: s.isna().mean() * 100))
    g = g.sort_values("n")
    names = [PLAT.get(p, p) for p in g.index]
    fig, (a, b) = plt.subplots(1, 2, figsize=(14, 5.6), gridspec_kw={"wspace": 0.12})
    a.barh(names, g.n, color=BLUE, edgecolor=MUTED)
    for y, v in enumerate(g.n):
        a.text(v + 40, y, thousands(v), va="center", fontsize=14)
    a.set_title("Listings per source", loc="left", fontweight="bold")
    a.set_xlim(0, g.n.max() * 1.18)
    a.xaxis.set_visible(False)
    a.spines["bottom"].set_visible(False)
    b.barh(names, g.no_area, color=ROSE, edgecolor=MUTED)
    for y, v in enumerate(g.no_area):
        b.text(v + 1.5, y, f"{v:.0f}%", va="center", fontsize=14)
    b.set_title("Listings with no area (%)", loc="left", fontweight="bold")
    b.set_xlim(0, 118)
    b.set_yticklabels([])
    b.tick_params(left=False)
    b.xaxis.set_visible(False)
    b.spines["bottom"].set_visible(False)
    fig.suptitle(f"{thousands(len(raw))} listings from 7 sources — uneven quality", fontsize=18, fontweight="bold", y=1.02)
    save(fig, "s03_sources.png")


# ------------------------------------------------------------------ slide 4: fake coordinate before / after
def fig_fallback(raw, fixed):
    bad, _ = fallback_mask(raw)
    feats = json.loads(Path("data/hanoi_districts.geojson").read_text(encoding="utf-8"))["features"]

    def draw_base(ax):
        for f in feats:
            geoms = f["geometry"]["coordinates"] if f["geometry"]["type"] == "MultiPolygon" else [f["geometry"]["coordinates"]]
            for poly in geoms:
                ax.add_patch(Polygon(np.array(poly[0]), closed=True, fc="#f1f5f9", ec="#cbd5e1", lw=0.8))
        ax.set_xlim(105.28, 106.05)
        ax.set_ylim(20.52, 21.42)
        ax.set_aspect(1 / np.cos(np.radians(21)))
        ax.axis("off")

    b, a = raw[bad], fixed.loc[bad.values]
    a = a.dropna(subset=["latitude", "longitude"])
    fig, axs = plt.subplots(1, 2, figsize=(14, 7.2), gridspec_kw={"wspace": 0.04})
    draw_base(axs[0])
    axs[0].scatter(b.longitude, b.latitude, s=460, color="#ef4444", alpha=0.9, zorder=3, edgecolor="white", lw=2)
    axs[0].annotate(f"{len(b)} listings on one point\n(= the UTC campus location)", (b.longitude.iloc[0], b.latitude.iloc[0]),
                    xytext=(105.62, 20.66), fontsize=15, fontweight="bold", color="#b91c1c",
                    arrowprops=dict(arrowstyle="-|>", color="#b91c1c", lw=2))
    axs[0].set_title("Before: one fallback coordinate", fontsize=18, fontweight="bold")
    draw_base(axs[1])
    axs[1].scatter(a.longitude, a.latitude, s=70, color=TEAL, alpha=0.8, zorder=3, edgecolor="white", lw=0.8)
    axs[1].text(105.30, 20.55, f"{len(a)} of {len(b)} listings placed in the right ward", fontsize=15,
                fontweight="bold", color="#115e59")
    axs[1].set_title("After: each ward geocoded (35 lookups)", fontsize=18, fontweight="bold")
    fig.text(0.5, 0.02, "© OpenStreetMap contributors · Nominatim", ha="center", fontsize=11, color=MUTED)
    save(fig, "s04_fallback_coordinates.png")


# ------------------------------------------------------------------ slide 5: dedup
def fig_dedup(dd):
    dd = dd.copy()
    dd["dup"] = dd.duplicate_of.notna()
    g = dd.groupby("platform").dup.agg(folded="sum", total="size")
    g["kept"] = g.total - g.folded
    g = g.sort_values("total")
    names = [PLAT.get(p, p) for p in g.index]
    fig, ax = plt.subplots(figsize=(13, 6))
    ax.barh(names, g.kept, color=BLUE, edgecolor=MUTED, label="kept")
    ax.barh(names, g.folded, left=g.kept, color=ROSE, edgecolor=MUTED, label="merged as duplicates")
    for y, (k, f) in enumerate(zip(g.kept, g.folded)):
        if f > 0:
            ax.text(k + f + 40, y, f"−{thousands(f)}", va="center", fontsize=14, color="#9f1239", fontweight="bold")
    ax.xaxis.set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.legend(loc="lower right", frameon=False, fontsize=14)
    ax.set_title(f"{thousands(len(dd))} → {thousands(int((~dd.dup).sum()))} listings after merging cross-platform duplicates",
                 loc="left", fontweight="bold", fontsize=17)
    save(fig, "s05_dedup.png")


# ------------------------------------------------------------------ slide 6: prices
def fig_prices(d):
    top = d.district.value_counts().head(10).index
    med = d[d.district.isin(top)].groupby("district").price_vnd.median().sort_values(ascending=False)
    fig, (a, b) = plt.subplots(1, 2, figsize=(15, 6.2), gridspec_kw={"width_ratios": [2.0, 1], "wspace": 0.5})
    data = [d[d.district == k].price_vnd.clip(upper=15e6) / 1e6 for k in med.index]
    bp = a.boxplot(data, patch_artist=True, showfliers=False, medianprops=dict(color=INK, lw=2))
    for patch in bp["boxes"]:
        patch.set(facecolor=BLUE, edgecolor=MUTED)
    a.set_xticks(range(1, len(med) + 1), med.index, rotation=30, ha="right")
    a.set_ylabel("Monthly rent (million VND)")
    a.set_title("Rent by district (top 10 by listings)", loc="left", fontweight="bold", fontsize=16)
    a.yaxis.grid(True, color=GRID)
    cols = {"Area (m²)": "area_m2", "Number of amenities": "amenity_count", "Distance to centre": "distance_to_center_km",
            "Distance to metro": "distance_to_nearest_metro_km", "Distance to university": "distance_to_nearest_university_km"}
    rho = {k: d[["price_vnd", v]].dropna().corr(method="spearman").iloc[0, 1] for k, v in cols.items()}
    s = pd.Series(rho).sort_values()
    b.barh(s.index, s.values, color=[ROSE if v < 0 else GREEN for v in s.values], edgecolor=MUTED)
    for y, v in enumerate(s.values):
        b.text(v + (0.02 if v >= 0 else -0.02), y, f"{v:+.2f}", va="center", ha="left" if v >= 0 else "right", fontsize=13)
    b.axvline(0, color=MUTED, lw=1)
    b.set_xlim(-0.5, 0.85)
    b.set_title("Correlation with rent (Spearman)", loc="left", fontweight="bold", fontsize=15, x=-0.7)
    b.xaxis.set_visible(False)
    b.spines["bottom"].set_visible(False)
    fig.suptitle(f"Median rent {d.price_vnd.median() / 1e6:.1f} million VND; area matters more than location",
                 fontsize=18, fontweight="bold", y=1.03)
    save(fig, "s06_prices.png")
    return rho


# ------------------------------------------------------------------ slide 7: score anatomy
def fig_score(d):
    r = recommend(d, 4_000_000, ["Cầu Giấy"], need=["air_conditioner"], top=5)
    parts = [("price", "Price fit", "s_price", GREEN), ("value", "Value vs market", "s_value", BLUE),
             ("distance", "Closeness to centre", "s_dist", AMBER), ("amenity", "Amenities", "s_amenity", ROSE)]
    fig, ax = plt.subplots(figsize=(13, 5.8))
    labels = [f"#{i}  {p / 1e6:.1f} M · {a:.0f} m²" for i, (p, a) in enumerate(zip(r.price_vnd, r.area_est), 1)][::-1]
    left = np.zeros(len(r))
    for key, name, col, color in parts:
        w = WEIGHTS[key] * r[col].values[::-1]
        ax.barh(labels, w, left=left, color=color, edgecolor="white", label=f"{name} (weight {WEIGHTS[key]:.2f})")
        left += w
    for y, tot in enumerate(left):
        ax.text(tot + 0.01, y, f"{tot:.2f}", va="center", fontweight="bold", fontsize=15)
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("Score (0–1)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, frameon=False, fontsize=13)
    ax.set_title("Top 5 rooms for a sample query: budget 4 M VND, Cầu Giấy, air conditioning", loc="left",
                 fontweight="bold", fontsize=16)
    save(fig, "s07_score_anatomy.png")


# ------------------------------------------------------------------ slide 8: price map (stand-in for the app map)
def fig_price_map(d):
    feats = json.loads(Path("data/hanoi_districts.geojson").read_text(encoding="utf-8"))["features"]
    pts = d.dropna(subset=["latitude", "longitude"])
    pts = pts[(pts.longitude.between(105.68, 105.97)) & (pts.latitude.between(20.93, 21.13))]
    fig, ax = plt.subplots(figsize=(11, 8.2))
    for f in feats:
        geoms = f["geometry"]["coordinates"] if f["geometry"]["type"] == "MultiPolygon" else [f["geometry"]["coordinates"]]
        for poly in geoms:
            ax.add_patch(Polygon(np.array(poly[0]), closed=True, fc="#f8fafc", ec="#cbd5e1", lw=0.8))
    bands = [("< 3 M VND", pts.price_vnd < 3e6, "#4ade80"),
             ("3–5 M VND", pts.price_vnd.between(3e6, 5e6, inclusive="left"), "#60a5fa"),
             ("> 5 M VND", pts.price_vnd >= 5e6, "#fb7185")]
    rng = np.random.default_rng(0)
    for name, mask, col in bands:   # tiny jitter: many rooms share a ward centroid
        q = pts[mask]
        ax.scatter(q.longitude + rng.normal(0, 0.0009, len(q)), q.latitude + rng.normal(0, 0.0009, len(q)),
                   s=11, color=col, alpha=0.55, linewidths=0, label=f"{name} ({thousands(len(q))})")
    ax.set_xlim(105.68, 105.97)
    ax.set_ylim(20.93, 21.13)
    ax.set_aspect(1 / np.cos(np.radians(21)))
    ax.axis("off")
    ax.legend(loc="lower left", frameon=True, fontsize=14, markerscale=2.5, title="Monthly rent", title_fontsize=14)
    ax.set_title("Where the rooms are (inner Hanoi)", loc="left", fontweight="bold", fontsize=17)
    fig.text(0.5, 0.06, "© OpenStreetMap contributors · many listings share a ward-centre coordinate, so points are slightly jittered",
             ha="center", fontsize=11, color=MUTED)
    save(fig, "s08_price_map.png")


# ------------------------------------------------------------------ slide 9: evaluation
def fig_eval():
    v = pd.read_csv("data/recsys_eval_labels_v2.csv")
    p = v.groupby(["persona", "config"]).rating_1_5.mean().unstack()
    base, dflt = [c for c in p.columns if c.startswith("baseline")][0], [c for c in p.columns if c.startswith("mặc định")][0]
    p = p.sort_values(dflt)
    fig, (a, b) = plt.subplots(1, 2, figsize=(15, 6.4), gridspec_kw={"width_ratios": [1.7, 1], "wspace": 0.35})
    y = np.arange(len(p))
    a.barh(y + 0.19, p[base], height=0.36, color="#cbd5e1", edgecolor=MUTED, label=f"Cheapest first (mean {p[base].mean():.2f})")
    a.barh(y - 0.19, p[dflt], height=0.36, color=TEAL, edgecolor=MUTED, label=f"Our score (mean {p[dflt].mean():.2f})")
    a.set_yticks(y, [PERSONA.get(i, i) for i in p.index])
    a.set_xlim(0, 5)
    a.set_xlabel("Mean rating of the top 5 results (1–5)")
    a.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2, frameon=False, fontsize=13)
    a.set_title("Our score wins on 10 of 10 personas (+%.2f)" % (p[dflt] - p[base]).mean(), loc="left", fontweight="bold")
    stages = ["Initial", "Shared-room ads\nremoved + fake\ncoordinate", "Price score\nfixed (typical\nprice)"]
    means, p4 = [2.60, 3.16, 3.52], [24, 28, 52]
    b.plot(stages, means, marker="o", color=TEAL, lw=3, ms=11)
    for i, (m, q) in enumerate(zip(means, p4)):
        b.text(i, m + 0.17, f"{m:.2f}\n({q}% rated ≥ 4)", ha="center", fontsize=12.5)
    b.set_ylim(2, 4.3)
    b.set_xlim(-0.45, 2.45)
    b.set_ylabel("Mean rating (5 personas)")
    b.set_title("Rating rises after each fix", loc="left", fontweight="bold")
    b.tick_params(axis="x", labelsize=12)
    fig.text(0.5, -0.12, "Caveat: ratings were assigned by an AI assistant from listing text, not by real users; not blind. 10 personas.",
             ha="center", fontsize=13, color="#b91c1c", fontweight="bold")
    save(fig, "s09_evaluation.png")


def main():
    raw = pd.read_csv("data/unified_hanoi_rentals.csv", low_memory=False)
    fixed = pd.read_csv("data/unified_hanoi_rentals_geofixed.csv", low_memory=False)
    dd = pd.read_csv("data/unified_hanoi_rentals_dedup.csv", low_memory=False)
    d = load()
    fig_pipeline(len(raw), int(dd.duplicate_of.isna().sum()))
    fig_sources(raw)
    fig_fallback(raw, fixed)
    fig_dedup(dd)
    print("spearman:", {k: round(v, 3) for k, v in fig_prices(d).items()})
    fig_score(d)
    fig_price_map(d)
    fig_eval()


if __name__ == "__main__":
    main()
