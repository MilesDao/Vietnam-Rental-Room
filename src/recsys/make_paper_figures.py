"""Figures for the written report (docs/latex/report.tex): vector PDFs at the report's text width, in its font.

    python -m src.recsys.make_paper_figures      # ~1 min -> docs/latex/figures/fig_*.pdf

Reads the prepared data and docs/report_numbers.json (python -m src.recsys.report_numbers), so the figures show
exactly the numbers the text quotes. Style: Latin Modern (the report's font, taken from the Tectonic cache when
present), Okabe-Ito colour-blind-safe colours, no titles inside figures (captions live in LaTeX), panel labels
(a), (b), intervals wherever the report gives one. The three diagrams (pipeline, ranker, metric example) are TikZ
files in docs/latex/figures/, not drawn here. The slide figures (make_slide_figures.py) are separate.
"""
import glob
import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("pdf")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager, patheffects  # noqa: E402
from matplotlib.ticker import FuncFormatter, NullFormatter  # noqa: E402
from sklearn.metrics.pairwise import linear_kernel  # noqa: E402

from src.recsys import price_model as pm  # noqa: E402
from src.recsys.prepare import OUT as DATA  # noqa: E402
from src.recsys.recommend import QUALITY, active_weights, load, recommend  # noqa: E402
from src.recsys.regeocode_fallback import load_polys  # noqa: E402
from src.recsys.similar import TEXT_W, Index  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/latex/figures"
NUMS = ROOT / "docs/report_numbers.json"
TEXT_W_IN = 15.8 / 2.54          # report text width (A4, 2.6 cm margins)
C = {"blue": "#0072B2", "orange": "#E69F00", "sky": "#56B4E9", "green": "#009E73", "verm": "#D55E00",
     "purple": "#CC79A7", "grey": "#6E6E6E", "light": "#C8C8C8", "ink": "#222222"}
NAMES = {"Facebook": "Facebook", "ChoTot.com": "Nhatot", "Mogi.vn": "Mogi", "YourHome.top": "YourHome",
         "Rencity.vn": "Rencity", "Alonhadat.vn": "Alonhadat", "Phongtro123.com": "Phongtro123"}
TYPES = {"Studio": "Studio", "Chung cư mini": "Mini-apartment block", "Phòng trọ": "Room", "Căn hộ": "Apartment",
         "Nhà nguyên căn": "Whole house"}
SIGNALS = {"price": "Price fit", "value": "Value vs. market", "distance": "Closeness", "amenity": "Amenities",
           "q_not_sublet": "Not a sublet", "q_has_address": "Street address given",
           "q_district_ok": "District matches address"}


def style():
    fonts = glob.glob(os.path.expandvars(r"%LOCALAPPDATA%/TectonicProject/Tectonic/cache/bundles/data/*/lmroman10-*.otf"))
    for f in fonts:
        font_manager.fontManager.addfont(f)
    plt.rcParams.update({
        # ponytail: Latin Modern from the Tectonic cache; falls back to DejaVu Serif on a machine without it
        "font.family": "Latin Modern Roman" if fonts else "DejaVu Serif", "mathtext.fontset": "cm",
        "font.size": 8.5, "axes.labelsize": 8.5, "axes.titlesize": 8.5, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
        "legend.fontsize": 7.5, "legend.frameon": False, "axes.linewidth": 0.6, "xtick.major.width": 0.6,
        "ytick.major.width": 0.6, "xtick.major.size": 2.5, "ytick.major.size": 2.5, "axes.spines.top": False,
        "axes.spines.right": False, "axes.edgecolor": C["ink"], "axes.labelcolor": C["ink"], "text.color": C["ink"],
        "xtick.color": C["ink"], "ytick.color": C["ink"], "axes.titlelocation": "left", "axes.titlepad": 4,
        "grid.color": "#E3E3E3", "grid.linewidth": 0.5, "axes.axisbelow": True, "pdf.fonttype": 42,
        "savefig.bbox": "tight", "savefig.pad_inches": 0.02, "savefig.dpi": 300, "figure.dpi": 150})


def save(fig, name):
    fig.savefig(OUT / name)
    plt.close(fig)
    print("wrote", OUT / name)


def thousands(ax, axis="x"):
    f = FuncFormatter(lambda v, _: f"{v:,.0f}")
    (ax.xaxis if axis == "x" else ax.yaxis).set_major_formatter(f)


def hbar_labels(ax, ys, vals, fmt, pad):
    for y, v in zip(ys, vals):
        ax.text(v + pad, y, fmt(v), va="center", fontsize=7)


# ---------------------------------------------------------------- data shared by several figures
def price_errors(d):
    """Out-of-fold errors of the fair-price model and of the median baseline, per training room (as in price_model)."""
    t = d[pm._train_rows(d) & d.fair_price.notna()].reset_index(drop=True)
    y = np.log(t.price_vnd.values)
    groups = pm.cv_groups(t)
    base = np.exp(pm._group_median_oof((t.house_type.fillna("") + "|" + t.district.fillna("")).values, y, groups))
    p = t.price_vnd.values
    return t, np.abs(t.fair_price.values - p) / p * 100, np.abs(base - p) / p * 100, groups


# ---------------------------------------------------------------- figures
def fig_sources(d):
    distinct = d[d.duplicate_of.isna()]
    rows = d.platform.value_counts()
    order = list(rows.index)
    no_area = distinct.groupby("platform").area_m2.apply(lambda s: s.isna().mean() * 100).reindex(order)
    dated = distinct.groupby("platform").days_old.apply(lambda s: s.notna().mean() * 100).reindex(order)
    fig, ax = plt.subplots(1, 3, figsize=(TEXT_W_IN, 1.9), sharey=True, gridspec_kw={"width_ratios": [1.35, 1, 1]})
    ys = np.arange(len(order))
    ax[0].barh(ys, rows.values, color=C["blue"], height=0.62)
    hbar_labels(ax[0], ys, rows.values, lambda v: f"{v:,.0f}", rows.max() * 0.02)
    ax[0].set_xlim(0, rows.max() * 1.22)
    thousands(ax[0])
    ax[0].set_title("(a) Listings")
    for a, vals, title, col in [(ax[1], no_area, "(b) No stated area (%)", C["verm"]),
                                (ax[2], dated, "(c) Posting date given (%)", C["green"])]:
        a.barh(ys, vals.values, color=col, height=0.62)
        hbar_labels(a, ys, vals.values, lambda v: f"{v:.0f}", 2.5)
        a.set_xlim(0, 118)
        a.set_xticks([0, 50, 100])
        a.set_title(title)
    ax[0].set_yticks(ys, [NAMES[p] for p in order])
    ax[0].invert_yaxis()
    for a in ax:
        a.grid(axis="x")
        a.tick_params(axis="y", length=0)
    fig.subplots_adjust(wspace=0.22)
    save(fig, "fig_sources.pdf")


def fig_dedup(d):
    plat = d.drop_duplicates("listing_id").set_index("listing_id").platform
    dup = d[d.duplicate_of.notna()]
    cross = dup.duplicate_of.map(plat) != dup.platform
    order = list(d.platform.value_counts().index)
    kept = d[d.duplicate_of.isna()].platform.value_counts().reindex(order, fill_value=0)
    same = dup[~cross].platform.value_counts().reindex(order, fill_value=0)
    other = dup[cross].platform.value_counts().reindex(order, fill_value=0)
    ys = np.arange(len(order))
    fig, ax = plt.subplots(figsize=(TEXT_W_IN * 1.12, 1.95))
    ax.barh(ys, kept, color=C["blue"], height=0.62, label="Kept (distinct room)")
    ax.barh(ys, same, left=kept, color=C["orange"], height=0.62, label="Removed: repost on the same site")
    ax.barh(ys, other, left=kept + same, color=C["verm"], height=0.62, label="Removed: same room on another site")
    for y, k, s, o in zip(ys, kept, same, other):
        txt = f"{k:,} kept" + (f", {s:,} repost" + ("s" if s > 1 else "") if s else "") + (f", {o} on another site" if o else "")
        ax.text(k + s + o + 40, y, txt, va="center", fontsize=7)
    ax.set_yticks(ys, [NAMES[p] for p in order])
    ax.invert_yaxis()
    ax.set_xlim(0, len(d[d.platform == order[0]]) * 1.45)
    thousands(ax)
    ax.set_xlabel("Listings")
    ax.grid(axis="x")
    ax.tick_params(axis="y", length=0)
    ax.legend(loc="lower right")
    save(fig, "fig_dedup.pdf")


def fig_price(d, err):
    t, ml, base, groups = err
    stated = t.area_m2.notna().values
    sets = [("All rooms", np.ones(len(t), bool)), ("Area stated", stated), ("No area", ~stated)]
    fig, ax = plt.subplots(1, 2, figsize=(TEXT_W_IN * 1.12, 2.75), gridspec_kw={"width_ratios": [1, 1.15], "wspace": 0.32})
    x = np.arange(len(sets))
    for k, (name, m) in enumerate(sets):
        ci = pm.cluster_ci(ml[m], base[m], groups[m])
        for off, vals, lo_hi, col, lab in [(-0.19, base[m], ci["b"], C["light"], "Median of room type × district"),
                                          (0.19, ml[m], ci["a"], C["blue"], "Gradient-boosted model")]:
            v = vals.mean()
            ax[0].bar(k + off, v, width=0.36, color=col, edgecolor=C["ink"], linewidth=0.4, label=lab if k == 0 else None)
            ax[0].errorbar(k + off, v, yerr=[[v - lo_hi[0]], [lo_hi[1] - v]], color=C["ink"], lw=0.7, capsize=2)
            ax[0].text(k + off, lo_hi[1] + 0.8, f"{v:.1f}", ha="center", va="bottom", fontsize=7)
    ax[0].set_xticks(x, [f"{n}\n(n = {int(m.sum()):,})" for n, m in sets], fontsize=7)
    ax[0].set_ylabel("Mean absolute percentage error (%)")
    ax[0].set_ylim(0, 56)
    ax[0].grid(axis="y")
    ax[0].legend(loc="upper left", ncol=1, fontsize=7)
    ax[0].set_title("(a) Cross-validated error (95% intervals)")
    ax[0].tick_params(axis="x", length=0)

    fair, ask = t.fair_price.values / 1e6, t.price_vnd.values / 1e6
    lim = (0.4, 60)
    xs = np.geomspace(*lim, 50)
    ax[1].fill_between(xs, xs * 0.85, xs * 1.15, color=C["green"], alpha=0.18, lw=0, label="±15% (“fair”)")
    ax[1].plot(xs, xs * 0.75, color=C["grey"], lw=0.6, ls="--", label="±25% (typical model error)")
    ax[1].plot(xs, xs * 1.25, color=C["grey"], lw=0.6, ls="--")
    ax[1].plot(xs, xs, color=C["ink"], lw=0.7)
    ax[1].scatter(fair, ask, s=1.6, color=C["blue"], alpha=0.28, lw=0, rasterized=True)
    ax[1].set_xscale("log")
    ax[1].set_yscale("log")
    ax[1].set_xlim(lim)
    ax[1].set_ylim(lim)
    ticks = [0.5, 1, 2, 5, 10, 20, 50]
    for axis in (ax[1].xaxis, ax[1].yaxis):
        axis.set_major_locator(matplotlib.ticker.FixedLocator(ticks))
        axis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        axis.set_minor_formatter(NullFormatter())
    ax[1].set_xlabel("Estimated fair rent (million VND per month)")
    ax[1].set_ylabel("Asking rent (million VND per month)")
    ax[1].text(0.03, 0.95, f"n = {len(t):,}", transform=ax[1].transAxes, ha="left", va="top", fontsize=7)
    ax[1].legend(loc="lower right", fontsize=7)
    ax[1].set_title("(b) Asking against estimated fair rent")
    ax[1].set_aspect("equal")
    save(fig, "fig_price.pdf")


def fig_errors(err):
    t, ml, _, groups = err
    band = pd.qcut(t.price_vnd / 1e6, 5)
    band_lab = band.cat.categories.map(lambda iv: f"{max(iv.left, 0.5):.1f}–{iv.right:.1f}")
    panels = [
        ("(a) By room type", t.house_type.map(TYPES), [v for v in TYPES.values()]),
        ("(b) By asking rent (million VND)", band.cat.rename_categories(list(band_lab)).astype(str), list(band_lab)),
        ("(c) By source", t.platform.map(NAMES), [NAMES[p] for p in t.platform.value_counts().index]),
    ]
    fig, ax = plt.subplots(1, 3, figsize=(TEXT_W_IN, 2.0), sharex=True, gridspec_kw={"wspace": 1.05})
    for a, (title, key, cats) in zip(ax, panels):
        key = key.values
        rows = []
        for c in cats:
            m = key == c
            if m.sum() >= 20:
                ci = pm.cluster_ci(ml[m], ml[m], groups[m])["a"]
                rows.append((c, ml[m].mean(), ci, int(m.sum())))
        ys = np.arange(len(rows))
        for y, (c, v, ci, n) in zip(ys, rows):
            a.plot(ci, [y, y], color=C["blue"], lw=1.2, solid_capstyle="butt")
            a.plot(v, y, "o", color=C["blue"], ms=3.2)
        a.axvline(ml.mean(), color=C["grey"], lw=0.6, ls="--")
        a.set_yticks(ys, [f"{c} ({n:,})" for c, _, _, n in rows])
        a.invert_yaxis()
        a.set_title(title)
        a.grid(axis="x")
        a.tick_params(axis="y", length=0)
        a.set_xlim(0, 60)
    ax[1].set_xlabel("Mean absolute percentage error (%), with 95% interval")
    save(fig, "fig_errors.pdf")


def fig_map(d):
    t = d[pm._train_rows(d) & d.value_pct.notna() & d.latitude.notna()]
    lon_lim, lat_lim = (105.72, 105.93), (20.93, 21.10)
    inside = t.longitude.between(*lon_lim) & t.latitude.between(*lat_lim)
    t = t[inside]
    fig, ax = plt.subplots(figsize=(TEXT_W_IN * 0.82, 4.3))
    for name, poly in load_polys():
        for g in getattr(poly, "geoms", [poly]):
            ax.plot(*g.exterior.xy, color="#9A9A9A", lw=0.45, zorder=1)
        pt = poly.representative_point()
        if lon_lim[0] < pt.x < lon_lim[1] and lat_lim[0] < pt.y < lat_lim[1]:
            from src.clean.sample_schema import short_district
            ax.text(pt.x, pt.y, short_district(name) or name, fontsize=6.5, color="#4A4A4A", ha="center", va="center",
                    zorder=3, style="italic", path_effects=[patheffects.withStroke(linewidth=2, foreground="white")])
    sc = ax.scatter(t.longitude, t.latitude, c=t.value_pct.clip(-50, 50), cmap="RdBu_r", vmin=-50, vmax=50, s=3,
                    lw=0, alpha=0.75, zorder=2, rasterized=True)
    ax.set_xlim(lon_lim)
    ax.set_ylim(lat_lim)
    ax.set_aspect(1 / np.cos(np.radians(21.0)))
    ax.set_xlabel("Longitude (°E)")
    ax.set_ylabel("Latitude (°N)")
    cb = fig.colorbar(sc, ax=ax, fraction=0.035, pad=0.02, ticks=[-50, -25, 0, 25, 50])
    cb.ax.set_yticklabels(["−50 or less", "−25", "0", "+25", "+50 or more"])
    cb.set_label("Asking rent relative to estimated fair rent (%)")
    cb.outline.set_linewidth(0.5)
    ax.text(0, -0.19, f"{len(t):,} rooms in the area shown. District boundaries: GADM. Coordinates partly geocoded with "
            "Nominatim, © OpenStreetMap contributors.", transform=ax.transAxes, fontsize=6, color=C["grey"])
    save(fig, "fig_residual_map.pdf")


def fig_text():
    D = load()
    idx = Index(D)
    q = "phòng có gác xép ban công"
    s = idx.text_scores(q, D.listing_id.tolist())
    top = np.argsort(-s)[:6]
    # a typical seed chosen by a fixed rule, not by how good its neighbours look: the Cầu Giấy studio with a stated
    # area whose rent is closest to the median rent of such studios (ties by id)
    pool = D[(D.house_type == "Studio") & (D.district == "Cầu Giấy") & D.area_m2.notna()]
    pool = pool.assign(gap=(pool.price_vnd - pool.price_vnd.median()).abs()).sort_values(["gap", "listing_id"])
    seed = pool.iloc[0]
    i = idx.pos[seed.listing_id]
    sim = TEXT_W * linear_kernel(idx.X[i], idx.X).ravel() + (1 - TEXT_W) / (1 + np.linalg.norm(idx.num - idx.num[i], axis=1))
    sim[i] = -1
    near = np.argsort(-sim)[:6]

    def label(r):
        title = " ".join(str(r.title).split())
        title = title if len(title) <= 40 else title[:39].rstrip() + "…"
        area = f"{r.area_est:.0f} m²" + ("*" if r.area_imputed else "")
        district = r.district if isinstance(r.district, str) else "–"
        return f"{title} · {r.price_vnd / 1e6:.1f} M · {area} · {district}"

    fig, ax = plt.subplots(2, 1, figsize=(TEXT_W_IN * 0.5, 3.4), gridspec_kw={"hspace": 0.5})
    for a, rows, vals, title, col in [
            (ax[0], top, s[top], f"(a) Search for “{q}”", C["blue"]),
            (ax[1], near, sim[near], "(b) Most similar to: " + label(seed), C["green"])]:
        ys = np.arange(len(rows))
        a.barh(ys, vals, color=col, height=0.6)
        hbar_labels(a, ys, vals, lambda v: f"{v:.2f}", 0.01)
        a.set_yticks(ys, [label(D.iloc[j]) for j in rows], fontsize=6.5)
        a.invert_yaxis()
        a.set_xlim(0, 1)
        a.grid(axis="x")
        a.tick_params(axis="y", length=0)
        a.set_title(title, fontsize=7.5, loc="right")
    ax[1].set_xlabel("Similarity (0 to 1)")
    save(fig, "fig_text.pdf")


def fig_ranker(nums):
    rep = nums["ranker"]["report"]
    coef, w = rep["coef_std"], rep["learned_weights"]
    keys = list(SIGNALS)
    fig, ax = plt.subplots(1, 2, figsize=(TEXT_W_IN * 0.86, 2.35), gridspec_kw={"width_ratios": [1, 1.1], "wspace": 1.05})
    ys = np.arange(len(keys))
    for y, k in zip(ys, keys):
        c = coef[k]
        a_col = C["blue"] if c["lo"] > 0 else C["grey"]
        ax[0].plot([c["lo"], c["hi"]], [y, y], color=a_col, lw=1.2, solid_capstyle="butt")
        ax[0].plot(c["coef"], y, "o", color=a_col, ms=3.2)
        ax[0].text(1.5, y, f"{w[k]:.2f}", va="center", ha="right", fontsize=7)
    ax[0].text(1.5, -0.95, "weight", ha="right", va="center", fontsize=6.5, style="italic")
    ax[0].set_ylim(len(keys) - 0.5, -1.35)
    ax[0].set_xlim(-0.6, 1.55)
    ax[0].set_xticks([-0.5, 0, 0.5, 1])
    ax[0].axvline(0, color=C["grey"], lw=0.6, ls="--")
    ax[0].set_yticks(ys, [SIGNALS[k] for k in keys])
    ax[0].set_xlabel("Standardised coefficient (95% interval)")
    ax[0].set_title("(a) What the ratings reward")
    ax[0].grid(axis="x")
    ax[0].tick_params(axis="y", length=0)

    r = recommend(load(), 4_000_000, ["Cầu Giấy"], need=["air_conditioner"], top=5, ranker="ml")
    wt = active_weights("ml")
    parts = [("Price fit", wt["price"] * r.s_price, C["blue"]), ("Closeness", wt["distance"] * r.s_dist, C["orange"]),
             ("Amenities", wt["amenity"] * r.s_amenity, C["green"]), ("Value vs. market", wt["value"] * r.s_value, C["purple"])]
    quality = sum(wt.get(k, 0) * r[k] for k in QUALITY)
    ys = np.arange(len(r))
    left = np.zeros(len(r))
    for name, v, col in parts:
        if v.abs().sum() == 0:
            continue
        ax[1].barh(ys, v, left=left, color=col, height=0.6, label=name)
        left += v.values
    for y, l, q in zip(ys, left, quality):
        ax[1].text(l + 0.008, y, f"+ {q:.2f} quality = {l + q:.2f}", va="center", fontsize=6.5)
    labels = [f"#{k + 1}  {row.price_vnd / 1e6:.1f} M, {row.area_est:.0f} m²{'*' if row.area_imputed else ''}, "
              f"{NAMES.get(row.platform, row.platform)}" for k, row in enumerate(r.itertuples())]
    ax[1].set_yticks(ys, labels)
    ax[1].invert_yaxis()
    ax[1].set_xlim(0, 0.8)
    ax[1].set_xlabel("Score contribution")
    ax[1].set_title("(b) Top five, 4 M budget, Cầu Giấy, air conditioning")
    ax[1].legend(loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=3, fontsize=6.5)
    ax[1].grid(axis="x")
    ax[1].tick_params(axis="y", length=0)
    save(fig, "fig_ranker_learned.pdf")


def fig_eval(nums):
    rep, boot = nums["ranker"]["report"], nums["ranker"]["bootstrap_over_searches"]
    rows = [("Cheapest first", rep["cheapest_first"]), ("Random order (expected)", rep["random"]),
            ("Nearest first", rep["nearest_first"]), ("Price fit + closeness", rep["price_plus_distance"]),
            ("Learned weights (held-out)", rep["learned_cv"]), ("Hand-set weights", rep["hand"])]
    fig, ax = plt.subplots(1, 2, figsize=(TEXT_W_IN * 0.9, 2.15), gridspec_kw={"width_ratios": [1, 1], "wspace": 0.95})
    ys = np.arange(len(rows))
    for y, (name, m) in zip(ys, rows):
        ax[0].plot([m["p@5"], m["ndcg@10"]], [y, y], color=C["light"], lw=1, zorder=1)
    ax[0].scatter([m["ndcg@10"] for _, m in rows], ys, color=C["blue"], s=14, zorder=2, label="NDCG@10")
    ax[0].scatter([m["p@5"] for _, m in rows], ys, color=C["orange"], marker="s", s=12, zorder=2, label="Precision at 5")
    for y, (_, m) in zip(ys, rows):
        ax[0].text(1.005, y, f"{m['ndcg@10']:.3f}", va="center", fontsize=6.5, transform=ax[0].get_yaxis_transform())
    ax[0].set_yticks(ys, [n for n, _ in rows])
    ax[0].set_xlim(0.4, 1.0)
    ax[0].set_xlabel("Score (higher is better)")
    ax[0].legend(loc="upper left", fontsize=6.5)
    ax[0].set_title("(a) Ranking quality, 250 AI-assigned ratings")
    ax[0].grid(axis="x")
    ax[0].tick_params(axis="y", length=0)

    comps = [("vs. random order", "learned_minus_random"), ("vs. cheapest first", "learned_minus_cheapest"),
             ("vs. nearest first", "learned_minus_nearest"), ("vs. price fit + closeness", "learned_minus_price_dist"),
             ("vs. hand-set weights", "learned_minus_hand")]
    ys = np.arange(len(comps))
    for y, (name, k) in zip(ys, comps):
        b = boot[k]
        col = C["blue"] if b["lo"] > 0 else C["grey"]
        ax[1].plot([b["lo"], b["hi"]], [y, y], color=col, lw=1.2, solid_capstyle="butt")
        ax[1].plot(b["mean"], y, "o", color=col, ms=3.2)
        ax[1].text(1.02, y, f"{b['mean']:+.3f}", va="center", fontsize=6.5, transform=ax[1].get_yaxis_transform())
    ax[1].axvline(0, color=C["grey"], lw=0.6, ls="--")
    ax[1].set_yticks(ys, [n for n, _ in comps])
    ax[1].invert_yaxis()
    ax[1].set_xlim(-0.15, 0.42)
    ax[1].set_xlabel("Learned minus other, NDCG@10 (95% interval)")
    ax[1].set_title("(b) Gain of the learned weights")
    ax[1].grid(axis="x")
    ax[1].tick_params(axis="y", length=0)
    save(fig, "fig_eval.pdf")


def main():
    style()
    OUT.mkdir(parents=True, exist_ok=True)
    d = pd.read_csv(DATA, low_memory=False, dtype={"contact_phone": str, "listing_id": str})
    nums = json.loads(NUMS.read_text(encoding="utf-8"))
    err = price_errors(d)
    fig_sources(d)
    fig_dedup(d)
    fig_price(d, err)
    fig_errors(err)
    fig_map(d)
    fig_text()
    fig_ranker(nums)
    fig_eval(nums)


if __name__ == "__main__":
    main()
