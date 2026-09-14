"""CLI: build data/processed/listings_clean.parquet from data/interim/parsed_*.parquet.

Usage:
    python -m src.clean.run_clean

docs/PLAN.md Phase 3. Only mogi (Tier 1) has been crawled so far, so the
Tier-2 cross-post dedup layer, the Tier1<->Tier2 overlap report, and the full
2025 admin-unit crosswalk are out of scope for this pass -- see the "Known
gaps" section the report writes out, rather than silently skipping them.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.clean.amenities import extract_amenities
from src.clean.dedup import find_duplicate_clusters, pick_canonical
from src.clean.outliers import flag_outliers
from src.clean.text_clean import ascii_fold, normalize_text

REPO_ROOT = Path(__file__).resolve().parents[2]
INTERIM_DIR = REPO_ROOT / "data" / "interim"
PROCESSED_PATH = REPO_ROOT / "data" / "processed" / "listings_clean.parquet"
REPORT_PATH = REPO_ROOT / "reports" / "cleaning_report.md"

log = logging.getLogger("run_clean")


def load_interim() -> pd.DataFrame:
    frames = [pd.read_parquet(p) for p in sorted(INTERIM_DIR.glob("parsed_*.parquet"))]
    if not frames:
        raise FileNotFoundError(f"no parsed_*.parquet under {INTERIM_DIR} -- run a crawl first")
    return pd.concat(frames, ignore_index=True).drop_duplicates(subset="listing_id", keep="last")


def run() -> dict:
    df = load_interim()
    n_raw = len(df)
    missing_before = df.isna().sum()

    df["title"] = df["title"].map(normalize_text)
    df["description"] = df["description"].map(normalize_text)
    df["address_raw"] = df["address_raw"].map(normalize_text)
    df["address_norm"] = df["address_raw"].map(ascii_fold)

    n_price_missing = int(df["price_vnd_month"].isna().sum())
    n_area_missing = int(df["area_m2"].isna().sum())
    df = df.dropna(subset=["price_vnd_month", "area_m2"]).reset_index(drop=True)
    n_after_missing_drop = len(df)

    df = flag_outliers(df)
    n_outliers_flagged = int(df["is_outlier"].sum())
    outlier_reason_counts = (
        df.loc[df["is_outlier"], "outlier_reason"]
        .str.split(";").explode().value_counts().to_dict()
    )

    amenity_rows = [
        extract_amenities(ascii_fold(t), ascii_fold(d))
        for t, d in zip(df["title"], df["description"])
    ]
    amenity_df = pd.DataFrame(amenity_rows, index=df.index)
    amenity_hit_rates = amenity_df.mean().round(3).to_dict()
    df = pd.concat([df, amenity_df], axis=1)

    cluster_map, dedup_stats = find_duplicate_clusters(df)
    df["cluster_id"] = df["listing_id"].map(cluster_map)
    n_clusters = df["cluster_id"].nunique()
    cluster_sizes = df.groupby("cluster_id").size()
    multi_clusters = cluster_sizes[cluster_sizes > 1].sort_values(ascending=False)
    sample_clusters = []
    for cid in multi_clusters.head(5).index:
        titles = df.loc[df["cluster_id"] == cid, "title"].tolist()
        sample_clusters.append({"cluster_id": cid, "n": len(titles), "titles": titles})

    df = pick_canonical(df)
    n_after_dedup = len(df)

    PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PROCESSED_PATH, index=False)

    stats = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "n_raw": n_raw,
        "missing_before": missing_before.to_dict(),
        "n_price_missing_dropped": n_price_missing,
        "n_area_missing_dropped": n_area_missing,
        "n_after_missing_drop": n_after_missing_drop,
        "n_outliers_flagged": n_outliers_flagged,
        "outlier_reason_counts": outlier_reason_counts,
        "amenity_hit_rates": amenity_hit_rates,
        "dedup_stats": dedup_stats,
        "n_clusters": int(n_clusters),
        "n_multi_member_clusters": int((cluster_sizes > 1).sum()),
        "largest_cluster_size": int(cluster_sizes.max()) if len(cluster_sizes) else 0,
        "sample_clusters": sample_clusters,
        "n_after_dedup": n_after_dedup,
    }
    write_report(stats)
    log.info("wrote %s (%d rows) and %s", PROCESSED_PATH, n_after_dedup, REPORT_PATH)
    return stats


def write_report(stats: dict) -> None:
    lines = [
        "# Cleaning report",
        "",
        f"Run at: {stats['run_at']}",
        f"Source: `data/interim/parsed_*.parquet` (Tier 1 only -- mogi.vn)",
        "",
        "## Row counts",
        "",
        f"- Raw (post-ingest dedupe on listing_id): {stats['n_raw']}",
        f"- Dropped, price unparseable/negotiable: {stats['n_price_missing_dropped']}",
        f"- Dropped, area unparseable: {stats['n_area_missing_dropped']}",
        f"- After missing-value drop: {stats['n_after_missing_drop']}",
        f"- Duplicate clusters found: {stats['n_clusters']} "
        f"({stats['n_multi_member_clusters']} with >1 member, "
        f"largest = {stats['largest_cluster_size']})",
        f"- Near-exact text matches (Jaccard >= 0.85): {stats['dedup_stats']['text_match_pairs']}",
        f"- Attribute matches (location+area+price): {stats['dedup_stats']['attribute_match_pairs']}",
        f"- **Final row count: {stats['n_after_dedup']}**",
        "",
        "## Missing values (pre-clean, raw corpus)",
        "",
        "| column | nulls |",
        "|---|---|",
    ]
    for col, n in stats["missing_before"].items():
        if n:
            lines.append(f"| {col} | {n} |")

    lines += [
        "",
        "## Outliers (flagged, not dropped)",
        "",
        f"Total flagged: {stats['n_outliers_flagged']}",
        "",
        "| reason | count |",
        "|---|---|",
    ]
    for reason, n in stats["outlier_reason_counts"].items():
        lines.append(f"| {reason} | {n} |")

    lines += [
        "",
        "## Amenity extraction hit rates",
        "",
        "Keyword lexicon in `src/clean/amenities.py`; NOT manually validated for",
        "precision/recall on a sample yet (PLAN.md Phase 3 checklist item -- backlog).",
        "",
        "| amenity | share of listings |",
        "|---|---|",
    ]
    for key, rate in stats["amenity_hit_rates"].items():
        lines.append(f"| {key} | {rate:.1%} |")

    lines += [
        "",
        "## Sample duplicate clusters (largest 5, for a manual spot-check)",
        "",
    ]
    if stats["sample_clusters"]:
        for c in stats["sample_clusters"]:
            lines.append(f"- cluster `{c['cluster_id']}` ({c['n']} listings):")
            for t in c["titles"]:
                lines.append(f"  - {t}")
    else:
        lines.append("(none found)")

    lines += [
        "",
        "## Known gaps (not built in this pass)",
        "",
        "- **Admin-unit crosswalk (Vietnam's 2025 63->34 province reorg, district",
        "  level dissolved)**: not built. `district`/`province` carry the legacy",
        "  labels as scraped, normalized only for whitespace/unicode -- no",
        "  `admin_code` column yet. Needs an authoritative crosswalk sourced into",
        "  `data/external/` before Phase 4 spatial joins should trust anything",
        "  beyond the raw legacy label.",
        "- **Image-hash (pHash/dHash) dedup layer**: not run. The corpus stores",
        "  `image_urls`, not downloaded image bytes, so there's nothing to hash yet.",
        "- **Tier-2 cross-post dedup + Tier1<->Tier2 overlap report**: not",
        "  applicable -- no Tier-2 (social) source has been crawled.",
        "- **Manual precision/recall validation** of the dedupe clusters and the",
        "  amenity lexicon (both called for explicitly in PLAN.md Phase 3): not",
        "  done by a human yet -- see the sample clusters above as a starting point.",
        "",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()


if __name__ == "__main__":
    main()
