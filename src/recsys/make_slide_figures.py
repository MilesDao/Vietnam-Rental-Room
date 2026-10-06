"""Figures for the slide deck (docs/SLIDES_PLAN.md, docs/SLIDES_SCRIPT.md) — English labels.

    python -m src.recsys.make_slide_figures        # writes docs/slides/figures/m*.png (main) and x*.png (backup)

Everything is computed from the current data files, so the numbers on the slides match the reports.
Needs: data/unified_hanoi_rentals_fresh.csv (python -m src.pipelines.merge_fresh), *_geofixed.csv, *_dedup.csv, data/hanoi_districts.geojson,
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

from src.recsys.recommend import QUALITY, active_weights, load, recommend, ranker_info
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


NL = "\n"   # newline for multi-line figure labels


def thousands(n):
    return f"{n:,.0f}"


# ------------------------------------------------------------------ slide 2: pipeline
def fig_pipeline(n_raw, n_dedup, mape):
    steps = [("Data", f"{thousands(n_raw)} listings"+"\n"+"from 7 sources", "#cbd5e1"),
             ("Prepare", "clean prices & links,\nhash phones,\nmerge duplicates"+"\n"+f"→ {thousands(n_dedup)} rooms", "#99f6e4"),
             ("Features", "area, room type,\ndistrict, amenities,\ndistances, text", "#99f6e4"),
             ("ML models", f"fair price (MAPE\n{mape:.0f}%), missing area,\nTF-IDF text model", "#99f6e4"),
             ("ML ranker", "learning to rank:\nweights learned\nfrom votes", "#99f6e4"),
             ("App", "search, map,\nsimilar rooms,\nsave & compare", "#99f6e4"),
             ("Feedback", "like / dislike\n→ more votes\n→ retrain", "#99f6e4")]
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
    ax.text(0.6, 0.7, "data source (earlier phases)", va="center", fontsize=12)
    ax.add_patch(plt.Rectangle((6.2, 0.55), 0.35, 0.3, fc="#99f6e4", ec=MUTED))
    ax.text(6.7, 0.7, "this project: data preparation, ML models, ML ranker, app, feedback loop", va="center", fontsize=12)
    save(fig, "m1_pipeline.png")


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
    save(fig, "m2_data_sources.png")


# ------------------------------------------------------------------ slide 4: fake coordinate before / after
def fig_fallback(raw, fixed):
    bad, _ = fallback_mask(raw)
    if not bad.any():   # the re-crawled data has no fake-coordinate rows; keep the figure made from the first dataset
        print("x5_coordinate_fix.png not redrawn: no fallback-coordinate rows in the current data")
        return
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
    save(fig, "x5_coordinate_fix.png")


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
    save(fig, "m3b_dedup.png")


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
    save(fig, "x2_prices_by_district.png")
    return rho


# ------------------------------------------------------------------ slides 6-7: the ML ranker
SIGNALS = ["price", "value", "distance", "amenity"] + QUALITY
SIGNAL_NAMES = {"price": "Price fit", "value": "Value vs market (ML fair price)", "distance": "Closeness",
                "amenity": "Amenities", "q_not_sublet": "Not a sublet ad", "q_has_address": "Has street address",
                "q_district_ok": "District matches address"}


def fig_ranker_how():
    """Schematic: from votes to weights to a ranking."""
    fig, ax = plt.subplots(figsize=(16, 7.4))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 7.4)
    ax.axis("off")

    def box(x, y, w, h, title, lines, color, fs=12):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.15", fc=color, ec=MUTED, lw=1.4))
        ax.text(x + w / 2, y + h - 0.35, title, ha="center", va="center", fontsize=14, fontweight="bold")
        ax.text(x + w / 2, y + h / 2 - 0.25, lines, ha="center", va="center", fontsize=fs, linespacing=1.35)

    def arrow(x1, y1, x2, y2):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=20, color=MUTED, lw=2))

    ax.text(0.1, 7.0, "TRAINING  (offline, once there are votes)", fontsize=15, fontweight="bold", color="#115e59")
    box(0.1, 4.3, 3.3, 2.3, "1. Votes", "a user sees a ranked list" + NL + "and presses like / dislike" + NL +
        "like = 1, dislike = 0", "#e2e8f0")
    box(4.1, 4.3, 3.9, 2.3, "2. Signals per room", "7 numbers in 0–1:" + NL + "price fit · ML value · closeness" + NL +
        "amenities · not sublet" + NL + "has address · district ok", "#bfdbfe")
    box(8.7, 4.3, 3.4, 2.3, "3. Logistic regression", "predicts P(like) from" + NL + "the 7 signals; keep the" + NL +
        "non-negative coefficients", "#99f6e4")
    box(12.7, 4.3, 3.2, 2.3, "4. Weights", "scale to sum 1:" + NL + "w₁ … w₇" + NL + "(saved to a file)", "#ddd6fe")
    for x1, x2 in [(3.4, 4.1), (8.0, 8.7), (12.1, 12.7)]:
        arrow(x1, 5.45, x2, 5.45)

    ax.text(0.1, 3.5, "RANKING  (every search in the app)", fontsize=15, fontweight="bold", color="#115e59")
    box(0.1, 0.4, 3.3, 2.7, "Hard filters", "budget · district" + NL + "min area · amenities" + NL + "chosen campus ≤ N km" + NL +
        "→ candidate rooms", "#e2e8f0")
    box(4.1, 0.4, 3.9, 2.7, "Score each room", "score = w₁·price fit" + NL + "+ w₂·value + w₃·closeness" + NL +
        "+ w₄·amenities + w₅…w₇·quality", "#bfdbfe")
    box(8.7, 0.4, 3.4, 2.7, "Sort", "highest score first;" + NL + "one room per building", "#99f6e4")
    box(12.7, 0.4, 3.2, 2.7, "Show + collect", "cards with like/dislike;" + NL + "new votes → retrain", "#ddd6fe")
    for x1, x2 in [(3.4, 4.1), (8.0, 8.7), (12.1, 12.7)]:
        arrow(x1, 1.75, x2, 1.75)
    arrow(14.3, 4.3, 14.3, 3.1)   # weights feed the scoring ... drawn to the scoring column
    ax.add_patch(FancyArrowPatch((14.3, 3.2), (6.05, 3.2), connectionstyle="arc3,rad=0", arrowstyle="-|>",
                                 mutation_scale=1, color="none", lw=0))
    ax.plot([14.3, 6.05], [3.2, 3.2], color=MUTED, lw=2, ls=(0, (6, 4)))
    arrow(6.05, 3.2, 6.05, 3.1)
    ax.text(10.2, 3.28, "learned weights are used here", fontsize=12, color=MUTED, ha="center")
    save(fig, "m6_ranker_how.png")


def fig_ranker_learned(d):
    info = ranker_info()
    w = active_weights()
    fig, (a, b) = plt.subplots(1, 2, figsize=(15.5, 6.4), gridspec_kw={"width_ratios": [1, 1.15], "wspace": 0.5})
    y = np.arange(len(SIGNALS))[::-1]
    vals = [w.get(k, 0) for k in SIGNALS]
    a.barh(y, vals, color=TEAL, edgecolor=MUTED)
    for yy, v in zip(y, vals):
        a.text(v + 0.01, yy, f"{v:.2f}", va="center", fontsize=13, fontweight="bold")
    a.set_yticks(y, [SIGNAL_NAMES[k] for k in SIGNALS])
    a.set_xlim(0, 0.6)
    a.set_xlabel("Learned weight (sum = 1)")
    a.set_title("What the ranker learned", loc="left", fontweight="bold", fontsize=15)

    r = recommend(d, 4_000_000, ["Cầu Giấy"], need=["air_conditioner"], top=5)
    parts = [("price", "s_price", GREEN), ("value", "s_value", BLUE), ("distance", "s_dist", AMBER),
             ("amenity", "s_amenity", ROSE)]
    labels = [f"#{i}  {p / 1e6:.1f} M · {ar:.0f} m²" for i, (p, ar) in enumerate(zip(r.price_vnd, r.area_est), 1)][::-1]
    left = np.zeros(len(r))
    for key, col, color in parts:
        x = w.get(key, 0) * r[col].values[::-1]
        b.barh(labels, x, left=left, color=color, edgecolor="white", label=SIGNAL_NAMES[key])
        left += x
    x = sum(w.get(k, 0) * r[k].values[::-1] for k in QUALITY)
    b.barh(labels, x, left=left, color="#a78bfa", edgecolor="white", label="Quality signals (3)")
    left += x
    for yy, tot in enumerate(left):
        b.text(tot + 0.01, yy, f"{tot:.2f}", va="center", fontweight="bold", fontsize=14)
    b.set_xlim(0, 1.08)
    b.set_xlabel("Score (0–1)")
    b.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3, frameon=False, fontsize=11)
    b.set_title("Top 5 for “4 M budget, Cầu Giấy, air conditioning”", loc="left", fontweight="bold", fontsize=15)
    src = (info or {}).get("source", "none")
    fig.text(0.5, -0.16, f"Trained on 250 votes (source: {src}, i.e. given by an AI assistant, not by users). The ML value signal got "
             "weight 0; quality signals are ≈1 for most rooms, so they mainly push sublet ads down.",
             ha="center", fontsize=12, color="#b91c1c", fontweight="bold")
    save(fig, "m6_ranker_learned.png")


# ------------------------------------------------------------------ slide 6: text model (search + similar rooms)
def fig_text_model(d):
    from src.recsys.similar import Index
    idx = Index(d)
    query = "phòng có gác xép ban công"
    cand = d.listing_id.tolist()
    sim = idx.text_scores(query, cand)
    top = np.argsort(-sim)[:7]
    seed = d[d.title.str.contains("Studio", case=False, na=False) & d.platform.eq("Phongtro123.com")].listing_id.iloc[3]
    sim_ids = idx.similar(seed, k=6)
    seed_row = d[d.listing_id == seed].iloc[0]
    cut = lambda t, n=46: (t[:n] + "…") if len(t) > n else t   # noqa: E731
    fig, (a, b) = plt.subplots(1, 2, figsize=(16, 6.2), gridspec_kw={"wspace": 0.6})
    ya = np.arange(len(top))[::-1]
    a.barh(ya, sim[top], color=BLUE, edgecolor=MUTED)
    a.set_yticks(ya, [cut(d.title.iloc[i]) for i in top], fontsize=11)
    for yy, i in zip(ya, top):
        a.text(sim[i] + 0.005, yy, f"{sim[i]:.2f}", va="center", fontsize=12)
    a.set_xlim(0, max(sim[top]) * 1.15)
    a.set_xlabel("Cosine similarity to the query (TF-IDF)")
    a.set_title(f"Free-text search: “{query}”", loc="left", fontweight="bold", fontsize=15)
    rows = d.set_index("listing_id").loc[sim_ids]
    yb = np.arange(len(rows))[::-1]
    b.barh(yb, np.linspace(1, 0.55, len(rows)), color=TEAL, alpha=0.0)
    b.axis("off")
    b.set_title("Similar rooms to this one", loc="left", fontweight="bold", fontsize=15)
    b.text(0, 1.0, f"Seed: {cut(seed_row.title, 52)}", fontsize=12.5, fontweight="bold", transform=b.transAxes, va="top")
    b.text(0, 0.95, f"{seed_row.price_vnd / 1e6:.1f} M · {seed_row.area_est:.0f} m² · {seed_row.district}", fontsize=12,
           color=MUTED, transform=b.transAxes, va="top")
    for i, (lid, r) in enumerate(rows.iterrows()):
        yy = 0.82 - i * 0.12
        b.text(0, yy, f"{i + 1}. {cut(r.title, 52)}", fontsize=12, transform=b.transAxes, va="top")
        b.text(0, yy - 0.05, f"    {r.price_vnd / 1e6:.1f} M · {r.area_est:.0f} m² · {r.district}", fontsize=11,
               color=MUTED, transform=b.transAxes, va="top")
    fig.suptitle("Text model: TF-IDF on character n-grams powers search and “similar rooms”", fontsize=18,
                 fontweight="bold", y=1.03)
    save(fig, "m5_text_model.png")


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
    save(fig, "x1_price_map.png")


# ------------------------------------------------------------------ slide 6: ML fair-price model
def fig_price_model(d):
    from src.recsys.price_model import REPORT, enrich
    if "price" not in REPORT:   # re-fit once to get the cross-validated errors (no files written)
        enrich(pd.read_csv("data/unified_hanoi_rentals_dedup.csv", low_memory=False), save=False)
    rep = REPORT["price"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(15, 6.2), gridspec_kw={"width_ratios": [1, 1.15], "wspace": 0.3})
    names = ["Median by\nroom type\n× district", "Ridge model\n(earlier\npipeline)*", "Our ML model\n(gradient\nboosting)"]
    vals = [rep["mape_group_median"], rep["mape_ridge_same_rows"], rep["mape_ml"]]
    a.bar(names, vals, color=["#cbd5e1", "#cbd5e1", TEAL], edgecolor=MUTED)
    for x, v in enumerate(vals):
        a.text(x, v + 0.8, f"{v:.1f}%", ha="center", fontsize=15, fontweight="bold")
    a.set_ylabel("Mean absolute % error of predicted rent")
    a.set_ylim(0, max(vals) * 1.2)
    a.set_title("Fair-price error (5-fold, out-of-fold)", loc="left", fontweight="bold")
    a.tick_params(axis="x", labelsize=12)
    a.text(0, -0.24, f"* Ridge judged on the {rep['n_ridge']:,} rows where it exists, in-sample; ML on the same rows: "
           f"{rep['mape_ml_same_rows']:.1f}%", transform=a.transAxes, fontsize=11, color=MUTED)
    t = d[d.duplicate_of.isna() & ~d.is_shared] if "duplicate_of" in d else d[~d.is_shared]
    t = t.sample(min(3000, len(t)), random_state=0)
    b.scatter(t.fair_price / 1e6, t.price_vnd / 1e6, s=8, alpha=0.35, color=BLUE, linewidths=0)
    lim = [0.5, 15]
    b.plot(lim, lim, color=INK, lw=1.5)
    b.fill_between(lim, [v * 0.85 for v in lim], [v * 1.15 for v in lim], color=TEAL, alpha=0.12)
    b.set_xscale("log")
    b.set_yscale("log")
    b.set_xlim(*lim)
    b.set_ylim(*lim)
    ticks = [1, 2, 3, 5, 8, 12]
    b.set_xticks(ticks, [str(x) for x in ticks])
    b.set_yticks(ticks, [str(x) for x in ticks])
    b.set_xlabel("Predicted fair rent (M VND)")
    b.set_ylabel("Asked rent (M VND)")
    b.set_title("Asked vs fair rent (shaded: ±15% = 'fair')", loc="left", fontweight="bold")
    b.text(0.6, 11, "above: dearer than\nsimilar rooms", fontsize=12, color="#9f1239")
    b.text(5, 0.7, "below: cheaper than\nsimilar rooms", fontsize=12, color="#115e59")
    fig.suptitle("An ML model estimates each room's fair rent → the 'value for money' score", fontsize=18,
                 fontweight="bold", y=1.03)
    save(fig, "m4_price_model.png")


# ------------------------------------------------------------------ slide 8: how the ranker is evaluated
def fig_metrics_toy():
    """A worked example of precision@5 and NDCG@10 on one search."""
    fig, ax = plt.subplots(figsize=(15, 5.2))
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 5.2)
    ax.axis("off")
    ranking = [1, 1, 0, 1, 0, 1, 0, 0, 1, 0]   # one ranked list, 1 = liked
    disc = 1 / np.log2(np.arange(2, 12))
    ax.text(0.1, 4.8, "One search, 10 rooms in the order the ranker puts them (green = liked, rose = disliked)",
            fontsize=14, fontweight="bold")
    for i, (g, dsc) in enumerate(zip(ranking, disc)):
        x = 0.1 + i * 1.45
        ax.add_patch(FancyBboxPatch((x, 3.1), 1.25, 1.1, boxstyle="round,pad=0.02,rounding_size=0.1",
                                    fc=GREEN if g else ROSE, ec=MUTED, lw=1.2))
        ax.text(x + 0.62, 3.86, f"rank {i + 1}", ha="center", fontsize=11, color=MUTED)
        ax.text(x + 0.62, 3.45, "like" if g else "dislike", ha="center", fontsize=13, fontweight="bold")
        ax.text(x + 0.62, 2.8, f"×{dsc:.2f}", ha="center", fontsize=11.5, color=INK)
    ax.text(0.1, 2.35, "Each position is discounted by 1 / log₂(rank + 1): a like at rank 1 counts fully, at rank 10 only 0.29.",
            fontsize=12, color=MUTED)
    dcg = sum(g * dsc for g, dsc in zip(ranking, disc))
    ideal = sorted(ranking, reverse=True)
    idcg = sum(g * dsc for g, dsc in zip(ideal, disc))
    p5 = sum(ranking[:5]) / 5
    lines = [("Precision@5", f"liked rooms among the first 5 ÷ 5 = {sum(ranking[:5])} ÷ 5 = {p5:.2f}", TEAL),
             ("DCG", f"sum of discounted likes = {dcg:.2f}", INK),
             ("Ideal DCG", f"all {sum(ranking)} liked rooms first = {idcg:.2f}", INK),
             ("NDCG@10", f"DCG ÷ ideal DCG = {dcg:.2f} ÷ {idcg:.2f} = {dcg / idcg:.2f}   (1.00 = perfect order)", TEAL)]
    for i, (name, txt, col) in enumerate(lines):
        ax.text(0.1, 1.75 - i * 0.5, name + ":", fontsize=14, fontweight="bold", color=col)
        ax.text(2.6, 1.75 - i * 0.5, txt, fontsize=14, color=INK)
    save(fig, "m7a_metrics_explained.png")


def fig_feedback_eval():
    from src.recsys import feedback, ltr
    ev = feedback.events(db="data/recsys_feedback_ai.sqlite")
    votes = ev[ev.action.isin(["up", "down"])]
    present = votes.listing_id.isin(set(load().listing_id)).mean()
    if present < 0.9:   # ltr.labelled() joins the quality signals by listing_id; missing rooms would silently get 1.0
        print(f"m7_evaluation.png / x4_per_search.png NOT redrawn: only {present:.0%} of the voted rooms are in the "
              "current data, so the evaluation would be distorted; keeping the figures made on the data the votes were cast on")
        return
    v = ltr.labelled(ev)
    rep, w = ltr.evaluate(v)
    per = ltr.per_search(v)
    caveat = ("Caveat: votes were given by an AI assistant from listing text (not by real users); "
              "only 10 searches, so differences must be judged with their intervals.")

    fig, (a, b) = plt.subplots(1, 2, figsize=(15, 6.2), gridspec_kw={"width_ratios": [1.15, 1], "wspace": 0.45})
    rankers = [("Random order", "random", "#e2e8f0"), ("Cheapest first", "cheapest_first", "#cbd5e1"),
               ("ML ranker (held-out)", "learned_cv", TEAL)]
    x = np.arange(2)
    for i, (name, key, col) in enumerate(rankers):
        vals = [rep[key]["ndcg@10"], rep[key]["p@5"]]
        bars = a.bar(x + (i - 1) * 0.27, vals, width=0.25, color=col, edgecolor=MUTED, label=name)
        for bx, val in zip(bars, vals):
            a.text(bx.get_x() + bx.get_width() / 2, val + 0.015, f"{val:.2f}", ha="center", fontsize=12)
    a.set_xticks(x, ["NDCG@10", "Precision@5"])
    a.set_ylim(0, 1.08)
    a.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3, frameon=False, fontsize=11)
    a.set_title(f"{rep['labels']} votes on {len(per)} searches (higher = better)", loc="left", fontweight="bold", fontsize=15)
    comps = [("ML ranker vs random order", "learned", "random", BLUE),
             ("ML ranker vs cheapest first", "learned", "cheapest", TEAL)]
    b.set_xlim(-0.1, 0.5)
    b.set_ylim(-0.3, 2.3)
    for i, (name, c1, c2, col) in enumerate(comps):
        yy = 1.5 - i * 1.2   # one row per comparison: title on top, interval below, numbers to the right
        r = ltr.bootstrap_diff(per, c1, c2)
        b.text(-0.1, yy + 0.38, name, fontsize=14, fontweight="bold", va="center")
        b.plot([r["lo"], r["hi"]], [yy, yy], color=col, lw=7, solid_capstyle="round", zorder=2)
        b.plot(r["mean"], yy, "o", color=INK, ms=12, zorder=3)
        b.text(r["hi"] + 0.02, yy, f"{r['mean']:+.2f}  [{r['lo']:+.2f}, {r['hi']:+.2f}]", va="center", fontsize=12.5)
    b.axvline(0, color="#b91c1c", lw=1.8, ls="--", zorder=1)
    b.text(0.003, 2.2, "0 = no gain", fontsize=11, color="#b91c1c", va="center")
    b.set_yticks([])
    b.spines["left"].set_visible(False)
    b.set_xlabel("Gain in NDCG@10 (dot = mean, bar = 95% bootstrap interval)")
    b.set_title("Is the gain real?  Both intervals exclude 0 → yes", loc="left", fontweight="bold", fontsize=15)
    fig.text(0.5, -0.08, caveat, ha="center", fontsize=12, color="#b91c1c", fontweight="bold")
    save(fig, "m7_evaluation.png")

    # backup: per-search view
    fig, (a, b) = plt.subplots(1, 2, figsize=(15, 6.2), gridspec_kw={"width_ratios": [1.3, 1], "wspace": 0.3})
    per = per.sort_values("learned")
    y = np.arange(len(per))
    for i, r in enumerate(per.itertuples()):
        a.plot([min(r.cheapest, r.learned), max(r.cheapest, r.learned)], [i, i], color="#cbd5e1", lw=3, zorder=1)
    a.scatter(per.cheapest, y, s=130, color="#94a3b8", zorder=3, label="Cheapest first")
    a.scatter(per.random, y, s=70, marker="D", color="#e2b714", zorder=3, label="Random order (expected)")
    a.scatter(per.learned, y, s=140, color=TEAL, zorder=3, label="ML ranker (held-out)")
    a.set_yticks(y, [f"search {s.replace('ai-q', '')}" for s in per.search])
    a.set_xlabel("NDCG@10 of that search")
    a.set_xlim(0.2, 1.05)
    a.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, frameon=False, fontsize=11)
    a.set_title(f"Per search: ML ranker beats cheapest-first in {(per.learned > per.cheapest).sum()} of {len(per)}",
                loc="left", fontweight="bold", fontsize=15)
    v = v.assign(bucket=np.where(v["rank"] <= 10, "Top 10", "Rank 11–25"))
    share = v.groupby("bucket").label.mean().reindex(["Top 10", "Rank 11–25"]) * 100
    b.bar(share.index, share.values, color=[TEAL, "#cbd5e1"], edgecolor=MUTED)
    for i, val in enumerate(share.values):
        b.text(i, val + 1.5, f"{val:.0f}%", ha="center", fontsize=15, fontweight="bold")
    b.set_ylim(0, 100)
    b.set_ylabel("Share rated 'like' (%)")
    b.set_title("Like rate in the lists that were rated", loc="left", fontweight="bold", fontsize=15)
    fig.text(0.5, -0.06, caveat, ha="center", fontsize=12, color="#b91c1c", fontweight="bold")
    save(fig, "x4_per_search.png")


def main():
    raw = pd.read_csv("data/unified_hanoi_rentals_fresh.csv", low_memory=False)
    fixed = pd.read_csv("data/unified_hanoi_rentals_geofixed.csv", low_memory=False)
    dd = pd.read_csv("data/unified_hanoi_rentals_dedup.csv", low_memory=False)
    d = load()
    own = d[~d.is_shared]   # distinct, non-shared rooms: what the fair-price model is judged on
    mape = float((abs(own.fair_price - own.price_vnd) / own.price_vnd).mean() * 100)
    fig_pipeline(len(raw), int(dd.duplicate_of.isna().sum()), mape)
    fig_sources(raw)
    fig_fallback(raw, fixed)
    fig_dedup(dd)
    print("spearman:", {k: round(v, 3) for k, v in fig_prices(d).items()})
    fig_price_model(d)
    fig_text_model(d)
    fig_ranker_how()
    fig_ranker_learned(d)
    fig_metrics_toy()
    fig_price_map(d)
    fig_feedback_eval()


if __name__ == "__main__":
    main()
