"""Outlier flagging for price/area (docs/PLAN.md Phase 3).

Flags, never silently deletes -- callers keep is_outlier/outlier_reason and
decide downstream whether to exclude flagged rows from a given analysis.
"""
from __future__ import annotations

import pandas as pd

PRICE_MIN_VND = 200_000
PRICE_MAX_VND = 100_000_000
AREA_MIN_M2 = 5.0
AREA_MAX_M2 = 500.0
MIN_DISTRICT_SAMPLE = 10  # below this, fall back to province-level IQR bounds
# Wide multiplier deliberately: this should only catch extreme mis-entries
# (typo'd zeros etc), not legitimate high-end/low-end listings -- price/m2
# genuinely varies a lot by exact location and room quality within a district.
IQR_MULTIPLIER = 3.0


def _iqr_bounds(s: pd.Series) -> tuple[float, float]:
    q1, q3 = s.quantile([0.25, 0.75])
    iqr = q3 - q1
    return q1 - IQR_MULTIPLIER * iqr, q3 + IQR_MULTIPLIER * iqr


def flag_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with is_outlier (bool) and outlier_reason (str|None) added.

    Assumes price_vnd_month and area_m2 are already non-null (rows lacking
    either should already have been dropped -- see run_clean.py).
    """
    df = df.copy()
    reasons: dict[int, list[str]] = {idx: [] for idx in df.index}

    def add_reason(mask: pd.Series, reason: str) -> None:
        for idx in df.index[mask.fillna(False)]:
            reasons[idx].append(reason)

    add_reason(df["price_vnd_month"] < PRICE_MIN_VND, "price_too_low")
    add_reason(df["price_vnd_month"] > PRICE_MAX_VND, "price_too_high")
    add_reason(df["area_m2"] < AREA_MIN_M2, "area_too_small")
    add_reason(df["area_m2"] > AREA_MAX_M2, "area_too_large")

    price_per_m2 = df["price_vnd_month"] / df["area_m2"]
    valid = price_per_m2.notna() & (df["area_m2"] > 0)
    valid_ppm = price_per_m2[valid]
    district_of = df.loc[valid, "district"]
    province_of = df.loc[valid, "province"]

    district_bounds = {
        d: _iqr_bounds(g) for d, g in valid_ppm.groupby(district_of) if len(g) >= MIN_DISTRICT_SAMPLE
    }
    province_bounds = {p: _iqr_bounds(g) for p, g in valid_ppm.groupby(province_of)}

    for idx in valid_ppm.index:
        lo, hi = district_bounds.get(district_of[idx], province_bounds[province_of[idx]])
        if not (lo <= valid_ppm[idx] <= hi):
            reasons[idx].append("price_per_m2_district_outlier")

    df["is_outlier"] = [bool(reasons[idx]) for idx in df.index]
    df["outlier_reason"] = [";".join(reasons[idx]) if reasons[idx] else None for idx in df.index]
    return df
