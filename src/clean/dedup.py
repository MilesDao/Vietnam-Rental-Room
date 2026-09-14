"""Duplicate detection and resolution (docs/PLAN.md Phase 3, layers 2/3/6).

Exact dedup (same listing_id) already happens at ingest (run_mogi.py's
flush_rows drops on listing_id). This module covers the next two layers --
near-exact text (shingle Jaccard) and attribute match (location + area +
price) -- merged into clusters, then resolved to one canonical row per
cluster.

Layer 4 (image pHash) and layer 5 (Tier-2 cross-post via phone_hash) are not
implemented: this corpus only stores image URLs (not downloaded image bytes),
and no Tier-2 source has been crawled yet. Both are noted in the cleaning
report rather than silently skipped.

Two deliberate deviations from PLAN.md's literal description, both found by
inspecting real output before trusting it (see reports/cleaning_report.md
"Known gaps"):

1. PLAN.md's resolution step says "take connected components" -- naive
   single-linkage clustering. On real mogi.vn data that chains: a listing
   agency posts many *different* rooms at the same standardized price/area
   with boilerplate-template titles, so A-B and B-C can each look like a
   match without A and C having anything in common, and single-linkage
   silently merges the whole chain into one cluster (observed: a 37-listing
   "cluster" spanning five different wards in HCMC that were genuinely
   different rooms). This module uses complete-linkage instead: two groups
   only merge if *every* cross-pair between them also matches, which caps
   chaining without needing a magic distance/diameter cutoff.
2. PLAN.md's attribute-match layer treats "lat/lon within 50m" as a location
   signal on its own. Empirically, mogi's embedded coordinates for some
   listings are ward-centroid, not rooftop -- multiple listings with
   different street addresses shared identical lat/lon to 6 decimal places.
   So this module requires normalized address *text* equality as the
   location signal instead of coordinate proximity.

Blocked by province to keep the pairwise comparison tractable. At Tier-1-only
scale (thousands of rows per province) exact O(n^2) Jaccard within a block
runs in under a minute; move to MinHash/LSH banding if a source pushes a
single province block past ~10-20k rows.
"""
from __future__ import annotations

import pandas as pd

from src.clean.text_clean import ascii_fold

SHINGLE_SIZE = 5
TEXT_JACCARD_THRESHOLD = 0.85
ATTR_AREA_DIFF_M2 = 1.0
ATTR_PRICE_DIFF_PCT = 0.05


def shingles(text: str | None, k: int = SHINGLE_SIZE) -> frozenset[str]:
    tokens = (ascii_fold(text) or "").split()
    if not tokens:
        return frozenset()
    if len(tokens) < k:
        return frozenset({" ".join(tokens)})
    return frozenset(" ".join(tokens[i:i + k]) for i in range(len(tokens) - k + 1))


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _attribute_match(a: dict, b: dict) -> bool:
    if abs(a["area_m2"] - b["area_m2"]) > ATTR_AREA_DIFF_M2:
        return False
    price_ref = max(a["price_vnd_month"], b["price_vnd_month"], 1)
    if abs(a["price_vnd_month"] - b["price_vnd_month"]) / price_ref > ATTR_PRICE_DIFF_PCT:
        return False
    return bool(a["address_norm"]) and a["address_norm"] == b["address_norm"]


def find_duplicate_clusters(df: pd.DataFrame) -> tuple[dict[str, str], dict[str, int]]:
    """Return ({listing_id: cluster_id}, stats). Singletons get their own cluster id.

    df must have: listing_id, title, description, province, area_m2,
    price_vnd_month, address_norm (already non-null for area_m2/price_vnd_month
    -- callers should have dropped those rows already).
    """
    attr_cols = ["listing_id", "area_m2", "price_vnd_month", "address_norm"]
    row_by_id = {r["listing_id"]: r for r in df[attr_cols].to_dict("records")}
    shingle_sets = {
        lid: shingles(f"{title} {desc}")
        for lid, title, desc in zip(df["listing_id"], df["title"], df["description"])
    }

    def is_match(lid_a: str, lid_b: str) -> tuple[bool, str]:
        if jaccard(shingle_sets[lid_a], shingle_sets[lid_b]) >= TEXT_JACCARD_THRESHOLD:
            return True, "text"
        if _attribute_match(row_by_id[lid_a], row_by_id[lid_b]):
            return True, "attribute"
        return False, ""

    # Each listing_id maps to the *same* set object shared by its whole group.
    groups: dict[str, set[str]] = {lid: {lid} for lid in df["listing_id"]}
    stats = {"text_match_pairs": 0, "attribute_match_pairs": 0}

    for _, block in df.groupby("province"):
        ids = block["listing_id"].tolist()
        n = len(ids)
        for i in range(n):
            lid_a = ids[i]
            for j in range(i + 1, n):
                lid_b = ids[j]
                group_a, group_b = groups[lid_a], groups[lid_b]
                if group_a is group_b:
                    continue
                matched, kind = is_match(lid_a, lid_b)
                if not matched:
                    continue
                # Complete-linkage: only actually merge if every member of A
                # matches every member of B, so one strong edge can't chain
                # two otherwise-unrelated groups together.
                if all(is_match(x, y)[0] for x in group_a for y in group_b):
                    merged = group_a | group_b
                    for lid in merged:
                        groups[lid] = merged
                    stats["text_match_pairs" if kind == "text" else "attribute_match_pairs"] += 1

    return {lid: min(groups[lid]) for lid in df["listing_id"]}, stats


def pick_canonical(df: pd.DataFrame, cluster_col: str = "cluster_id") -> pd.DataFrame:
    """Collapse each cluster to one row: most non-null fields, then most recent crawl.

    Adds n_duplicates (rows folded into this one, i.e. cluster size - 1).
    """
    df = df.copy()
    df["_nonnull"] = df.notna().sum(axis=1)
    df = df.sort_values(["_nonnull", "crawled_at"], ascending=[False, False])
    dup_counts = df.groupby(cluster_col).size().rename("n_duplicates") - 1
    canonical = df.drop_duplicates(subset=cluster_col, keep="first").drop(columns="_nonnull")
    canonical = canonical.merge(dup_counts, left_on=cluster_col, right_index=True)
    return canonical.reset_index(drop=True)
