"""Every number the written report quotes, from the prepared data, in one JSON (single source of truth).

    python -m src.recsys.report_numbers      # ~2 min -> docs/report_numbers.json + docs/labelling/*.csv

Sections: data, freshness, duplicates, price/area models (with 95% cluster-bootstrap intervals), value tiers,
ranker evaluation and link check (with Wilson intervals). Also writes two sheets a person must fill in:
docs/labelling/duplicate_pairs.csv (is each merged pair really one room?) and docs/labelling/facebook_links.csv
(does each Facebook link open the right post?). Nothing here is labelled by a model.

The ranker is evaluated on the data the votes were cast on (the 2026-10-06 backup of the prepared file), because
ltr.labelled() joins the quality signals by listing_id and only 40% of the voted rooms survive in the new data.
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from src.recsys import ltr, price_model
from src.recsys.feedback import events
from src.recsys.prepare import OUT
from src.recsys.recommend import load

ROOT = Path(__file__).resolve().parents[2]
VOTE_DATA = ROOT / "data/unified_hanoi_rentals_dedup.csv.bak-2026-10-06"   # the file the 250 AI votes were cast on
AI_VOTES = ROOT / "data/recsys_feedback_ai.sqlite"
LINK_CHECKS = {"before": ROOT / "data/interim/recrawl_2026-10/baseline.txt",
               "after": ROOT / "data/interim/recrawl_2026-10/final.txt"}
DOCS = ROOT / "docs"
SEED = 0


def wilson(k, n, z=1.96):
    """95% Wilson score interval for k successes out of n, in percent."""
    if n == 0:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(100 * max(0.0, centre - half), 1), round(100 * min(1.0, centre + half), 1)]


def link_check(path):
    """Parse a verify_sample table: platform, n, link_ok%, image_ok% (n/a when not testable)."""
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split()
        if len(parts) != 4:
            continue
        name, n = parts[0], int(parts[1])
        rows[name] = {"n": n}
        for key, val in (("link", parts[2]), ("image", parts[3])):
            if val == "n/a":
                rows[name][key] = None
                continue
            k = round(float(val) * n / 100)
            rows[name][key] = {"ok": k, "pct": round(100 * k / n, 1), "ci95": wilson(k, n)}
    return rows


def data_section(raw, d):
    distinct = d[d.duplicate_of.isna()]
    by = lambda s: {k: int(v) for k, v in s.items()}
    return {"rows": int(len(d)), "distinct_rooms": int(len(distinct)),
            "rows_by_platform": by(d.platform.value_counts()),
            "distinct_by_platform": by(distinct.platform.value_counts()),
            "house_types_distinct": by(distinct.house_type.value_counts()),
            "area_missing_share_distinct": round(float(distinct.area_m2.isna().mean()), 3),
            "area_missing_by_platform": {k: round(float(v), 3)
                                         for k, v in distinct.groupby("platform").area_m2.apply(lambda s: s.isna().mean()).items()},
            "facebook_share_rows": round(float((d.platform == "Facebook").mean()), 3),
            "price_quantiles_m_vnd": {str(q): round(float(v) / 1e6, 2)
                                      for q, v in distinct.price_vnd.quantile([.5, .9, .95, .99]).items()},
            "rows_before_prepare": int(len(raw))}


def freshness_section(d):
    distinct = d[d.duplicate_of.isna()]
    dated = distinct.days_old.notna()
    age = distinct.loc[dated, "days_old"]
    return {"dated_share_rows": round(float(d.days_old.notna().mean()), 3),
            "dated_share_distinct": round(float(dated.mean()), 3),
            "dated_share_by_platform": {k: round(float(v), 3)
                                        for k, v in distinct.groupby("platform").days_old.apply(lambda s: s.notna().mean()).items()},
            "age_days_quantiles_dated": {str(q): float(v) for q, v in age.quantile([.25, .5, .75, .9, 1.0]).items()},
            "snapshot_newest_post": str(pd.to_datetime(d.posted_at).max().date()),
            "max_age_filter_days": 180,
            "dropped_by_age_filter": 0}


def duplicate_section(d):
    plat = d.drop_duplicates("listing_id").set_index("listing_id").platform
    x = d[d.duplicate_of.notna()]
    target = x.duplicate_of.map(plat)
    cross = target != x.platform
    phones = d[d.contact_phone.astype(str).str.fullmatch(r"[0-9a-f]{16}")]
    multi = phones.groupby("contact_phone").platform.nunique()
    return {"duplicates": int(len(x)), "same_platform": int((~cross).sum()), "cross_platform": int(cross.sum()),
            "same_platform_by_platform": {k: int(v) for k, v in x[~cross].platform.value_counts().items()},
            "cross_platform_pairs": {f"{a} -> {b}": int(n) for (a, b), n in
                                     pd.Series(list(zip(x[cross].platform, target[cross]))).value_counts().items()},
            "posters_on_2plus_sites": int((multi > 1).sum()),
            "rows_of_those_posters": int(phones.contact_phone.isin(multi[multi > 1].index).sum()),
            "phone_hash_coverage_by_platform": {k: round(float(v), 3) for k, v in
                                                d.groupby("platform").contact_phone.apply(lambda s: s.notna().mean()).items()}}


def tier_section(d):
    m = d[d.duplicate_of.isna() & ~d.is_shared & d.value_pct.notna()]
    share = m.market_value_tier.value_counts(normalize=True)
    return {"n": int(len(m)), "share": {k: round(float(v), 3) for k, v in share.items()},
            "abs_value_pct_le_15": round(float((m.value_pct.abs() <= 15).mean()), 3)}


def error_section(d):
    """Where the fair-price model is wrong. The prepared file's fair_price is out-of-fold for training rooms."""
    t = d[d.duplicate_of.isna() & ~d.is_shared & d.price_vnd.notna() & d.fair_price.notna()].copy()
    t["ape"] = (t.fair_price - t.price_vnd).abs() / t.price_vnd * 100
    t["band"] = pd.qcut(t.price_vnd / 1e6, 5).astype(str)

    def by(col, min_n=1):
        g = t.groupby(col).ape.agg(["size", "mean", "median"])
        g = g[g["size"] >= min_n].sort_values("mean")
        return {str(k): {"n": int(r["size"]), "mape": round(float(r["mean"]), 1), "median_ape": round(float(r["median"]), 1)}
                for k, r in g.iterrows()}

    worst = t.nlargest(10, "ape")
    under = t.fair_price < t.price_vnd
    return {"n": int(len(t)), "median_ape": round(float(t.ape.median()), 1),
            "share_ape_over_50": round(float((t.ape > 50).mean()), 3),
            "by_house_type": by("house_type"), "by_price_band_m_vnd": by("band"),
            "by_district_min100": by("district", 100),
            "worst10": [{"listing_id": r.listing_id, "platform": r.platform, "house_type": r.house_type,
                         "price_m": round(r.price_vnd / 1e6, 2), "fair_m": round(r.fair_price / 1e6, 2),
                         "area_m2": None if pd.isna(r.area_m2) else float(r.area_m2), "title": str(r.title)[:90]}
                        for r in worst.itertuples()],
            "worst100_fair_below_price_share": round(float(under[t.nlargest(100, "ape").index].mean()), 3)}


def ranker_section():
    ltr.load = lambda: load(VOTE_DATA)   # quality signals from the data the votes were cast on
    v = ltr.labelled(events(db=AI_VOTES))
    rep, w = ltr.evaluate(v)
    per = ltr.per_search(v)
    pairs = [("learned", "random"), ("learned", "cheapest"), ("learned", "nearest"), ("learned", "price_dist"),
             ("learned", "hand"), ("hand", "nearest"), ("hand", "price_dist")]
    boot = {f"{a}_minus_{b}": {k: round(val, 3) if isinstance(val, float) else val
                               for k, val in ltr.bootstrap_diff(per, a, b).items()} for a, b in pairs}
    covered = float(v.listing_id.isin(load(VOTE_DATA).listing_id).mean())
    return {"labels_from": "AI-assigned votes (not users)", "data": VOTE_DATA.name,
            "voted_rooms_found_in_vote_data": round(covered, 3),
            "voted_rooms_in_current_data": round(float(v.listing_id.isin(load(OUT).listing_id).mean()), 3),
            "report": rep, "bootstrap_over_searches": boot,
            "per_search_ndcg": per.round(3).to_dict("records")}


def sheet_result(path, col):
    """Counts of the answers a person typed into `col` (empty sheet -> pending)."""
    answers = pd.read_csv(path, dtype=str, keep_default_na=False)[col].str.strip().str.lower()
    filled = answers[answers != ""]
    res = {"filled": int(len(filled)), "of": int(len(answers)), "counts": filled.value_counts().to_dict()}
    decided = filled[filled.isin(["yes", "no"])]   # "unsure" and "login wall" are reported but not scored
    if len(decided):
        k = int((decided == "yes").sum())
        res.update(decided=int(len(decided)), yes_pct=round(100 * k / len(decided), 1), ci95=wilson(k, len(decided)))
    return res


def labelling_sheets(d):
    """Write each sheet once; never overwrite a sheet that exists (it may hold a person's answers) - read it."""
    out = DOCS / "labelling"
    out.mkdir(parents=True, exist_ok=True)
    dup_path, fb_path = out / "duplicate_pairs.csv", out / "facebook_links.csv"
    dup_col, fb_col = "same_room (yes/no/unsure)", "opens_right_post (yes/no/login wall)"
    if not dup_path.exists():
        write_duplicate_sheet(d, dup_path, dup_col)
    if not fb_path.exists():
        fb = d[(d.platform == "Facebook") & d.listing_url.notna()].sample(25, random_state=SEED)
        fb[["listing_id", "title", "price_vnd", "listing_url"]].assign(
            **{fb_col: "", "image_shown_matches (yes/no/none)": ""}).to_csv(fb_path, index=False, encoding="utf-8-sig")
    return {"duplicate_pairs": sheet_result(dup_path, dup_col), "facebook_links": sheet_result(fb_path, fb_col),
            "seed": SEED}


def write_duplicate_sheet(d, path, col):
    """All cross-platform merged pairs plus a random sample of same-platform ones, 50 in total."""
    keep = d.drop_duplicates("listing_id").set_index("listing_id")
    x = d[d.duplicate_of.notna()]
    cross = x[x.duplicate_of.map(keep.platform) != x.platform]
    same = x.drop(cross.index).sample(50 - len(cross), random_state=SEED)
    rows = []
    for _, r in pd.concat([cross, same]).iterrows():
        k = keep.loc[r.duplicate_of]
        rows.append({"listing_a": r.listing_id, "listing_b": r.duplicate_of, "platform_a": r.platform,
                     "platform_b": k.platform, "price_a": r.price_vnd, "price_b": k.price_vnd,
                     "area_a": r.area_m2, "area_b": k.area_m2, "title_a": r.title, "title_b": k.title,
                     "address_a": r.address, "address_b": k.address, "url_a": r.listing_url, "url_b": k.listing_url,
                     col: ""})
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def main():
    d = pd.read_csv(OUT, low_memory=False, dtype={"contact_phone": str, "listing_id": str})
    raw = pd.read_csv(ROOT / "data/unified_hanoi_rentals_fresh.csv", low_memory=False, usecols=["listing_id"])
    nums = {"data": data_section(raw, d), "freshness": freshness_section(d), "duplicates": duplicate_section(d),
            "value_tiers": tier_section(d), "errors": error_section(d)}
    base = d.drop(columns=["fair_price", "value_pct", "market_value_tier", "area_est", "area_imputed", "is_shared"],
                  errors="ignore")
    price_model.enrich(base, save=False)
    nums["models"] = price_model.REPORT
    nums["ranker"] = ranker_section()
    nums["link_check"] = {k: link_check(p) for k, p in LINK_CHECKS.items()}
    nums["labelling_sheets"] = labelling_sheets(d)
    path = DOCS / "report_numbers.json"
    # keep the sections other scripts own (price_experiments.py, simulate_users.py); replace only ours
    merged = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    merged.update(nums)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
