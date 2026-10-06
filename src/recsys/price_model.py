"""ML models used by the recommender: missing-area estimate and fair-price ("value for money").

    python -m src.recsys.price_model --report      # cross-validated errors vs simple baselines

Both are gradient-boosted trees (sklearn HistGradientBoostingRegressor) on log targets, trained only on
distinct rooms (no cross-platform duplicates) that are not per-bed/shared ads. Every training row gets an
*out-of-fold* prediction (5 folds grouped by poster phone hash, else by ~50 m cell, so one poster's or one
building's near-copies are never on both sides), so a room's own price never leaks into its fair price;
other rows are predicted by a model fit on all training rows.

- Area model: replaces the house-type x price-quintile median only if its CV error is lower. It uses the
  price, so its area_est is for display/scoring only and is NOT an input of the fair-price model.
- Fair-price model: uses the stated area (missing when unknown), fair_price, value_pct = (price / fair_price - 1) * 100 (negative = cheaper than similar
  rooms), and market_value_tier at +-15 %. This replaces the branch's Ridge residual, which was missing for
  37 % of rows and stale for the rows whose location was repaired.
"""
import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold, KFold

from src.recsys.recommend import AMENITIES, mark_shared

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "data/models"
CATS = ["house_type", "district", "platform"]
DIST = ["distance_to_center_km", "distance_to_nearest_metro_km", "distance_to_nearest_university_km"]
TIERS = ["Giá hời (Bargain < -15%)", "Giá hợp lý (Fair Market ±15%)", "Giá cao (Premium > +15%)"]
REPORT = {}   # filled by enrich(); printed by --report and quoted in the final report


def _model():
    return HistGradientBoostingRegressor(categorical_features="from_dtype", max_iter=400, learning_rate=0.05,
                                         l2_regularization=1.0, random_state=0)


def _X(d, cols):
    X = d[cols].copy()
    for c in cols:
        if c in CATS:
            X[c] = X[c].fillna("?").astype("category")
        else:
            X[c] = pd.to_numeric(X[c], errors="coerce").astype(float)
    return X


def cv_groups(d):
    """Fold groups so near-copies never sit on both sides of a split: one poster (phone hash) is one group,
    otherwise one ~50 m cell (same building / same ward-centroid point)."""
    alone = pd.Series(["row:" + str(i) for i in range(len(d))], index=d.index)   # nothing to group by
    phone = d["contact_phone"] if "contact_phone" in d else pd.Series(np.nan, index=d.index)
    cell = pd.Series(np.nan, index=d.index, dtype=object)
    if {"latitude", "longitude"} <= set(d):
        lat = (pd.to_numeric(d.latitude, errors="coerce") / 0.0005).round()
        lon = (pd.to_numeric(d.longitude, errors="coerce") / 0.0005).round()
        ok = lat.notna() & lon.notna()
        cell[ok] = "geo:" + lat[ok].astype(int).astype(str) + ":" + lon[ok].astype(int).astype(str)
    return phone.where(phone.notna(), cell).fillna(alone).values


def _splits(n, groups, k=5):
    if groups is None:
        return KFold(k, shuffle=True, random_state=0).split(np.zeros(n))
    return GroupKFold(k).split(np.zeros(n), groups=groups)


def _oof(X, y, groups=None, k=5):
    pred = np.empty(len(y))
    for tr, te in _splits(len(y), groups, k):
        pred[te] = _model().fit(X.iloc[tr], y[tr]).predict(X.iloc[te])
    return pred


def _group_median_oof(keys, y, groups=None, k=5):
    """Baseline: median of the same group in the training folds (global median if the group is absent)."""
    pred = np.empty(len(y))
    keys = pd.Series(keys).reset_index(drop=True)
    for tr, te in _splits(len(y), groups, k):
        med = pd.Series(y[tr]).groupby(keys.iloc[tr].values).median()
        pred[te] = keys.iloc[te].map(med).fillna(np.median(y[tr])).values
    return pred


def _train_rows(d):
    distinct = d.duplicate_of.isna() if "duplicate_of" in d else True
    return distinct & ~d.is_shared & d.price_vnd.notna()


def add_area(d):
    d = d.copy()
    train = _train_rows(d) & d.area_m2.notna()
    cols = CATS + AMENITIES + DIST
    X = _X(d, cols).assign(log_price=np.log(d.price_vnd))
    y = np.log(d.loc[train, "area_m2"].values)
    groups = cv_groups(d[train])
    ml = np.exp(_oof(X[train].reset_index(drop=True), y, groups))
    q = pd.qcut(d.price_vnd, 5, labels=False, duplicates="drop").astype(str)
    base = _group_median_oof((d.house_type.fillna("") + "|" + q)[train].values, d.loc[train, "area_m2"].values, groups)
    true = d.loc[train, "area_m2"].values
    mae_ml, mae_base = float(np.mean(np.abs(ml - true))), float(np.mean(np.abs(base - true)))
    REPORT["area"] = {"n_train": int(train.sum()), "mae_ml_m2": round(mae_ml, 2), "mae_group_median_m2": round(mae_base, 2)}
    if mae_ml < mae_base:
        guess = np.exp(_model().fit(X[train], y).predict(X))
        method = "gradient-boosted trees"
    else:
        guess = d.groupby([d.house_type.fillna(""), q]).area_m2.transform("median").fillna(d.area_m2.median()).values
        method = "house type x price-quintile median"
    REPORT["area"]["method_used"] = method
    d["area_imputed"] = d.area_m2.isna()
    d["area_est"] = d.area_m2.fillna(pd.Series(np.round(guess, 1), index=d.index))
    return d


def add_fair_price(d, save=True):
    d = d.copy()
    train = _train_rows(d)
    # The stated area only, NaN when unknown (the trees handle missing values). area_est must not be used:
    # it is estimated from the room's own price, which would leak that price into its fair price.
    cols = CATS + AMENITIES + DIST + ["area_m2"]
    X = _X(d, cols)
    y = np.log(d.loc[train, "price_vnd"].values)
    groups = cv_groups(d[train])
    pred = pd.Series(np.nan, index=d.index)
    pred[train] = _oof(X[train].reset_index(drop=True), y, groups)
    full = _model().fit(X[train], y)
    if (~train).any():
        pred[~train] = full.predict(X[~train])
    d["fair_price"] = np.exp(pred).round(-3)
    d["value_pct"] = ((d.price_vnd / d.fair_price - 1) * 100).round(1)
    d["market_value_tier"] = pd.cut(d.value_pct, [-np.inf, -15, 15, np.inf], labels=TIERS).astype(str)

    price = d.loc[train, "price_vnd"].values
    ml = np.exp(pred[train].values)
    base = np.exp(_group_median_oof((d.house_type.fillna("") + "|" + d.district.fillna(""))[train].values, y, groups))
    ape_ml, ape_base = np.abs(ml - price) / price, np.abs(base - price) / price
    rep = {"n_train": int(train.sum()), "cv": "GroupKFold(5) by phone hash, else ~50 m cell",
           "mape_ml": round(float(ape_ml.mean()) * 100, 1),
           "mae_ml_vnd": round(float(np.mean(np.abs(ml - price))), -3),
           "mape_group_median": round(float(ape_base.mean()) * 100, 1),
           "mae_group_median_vnd": round(float(np.mean(np.abs(base - price))), -3)}
    stated = d.loc[train, "area_m2"].notna().values
    for name, m in (("area_stated", stated), ("area_missing", ~stated)):
        rep[name] = {"n": int(m.sum()), "mape_ml": round(float(ape_ml[m].mean()) * 100, 1),
                     "mape_group_median": round(float(ape_base[m].mean()) * 100, 1)}
    plat = d.loc[train, "platform"].fillna("?").values
    rep["by_platform"] = {p: {"n": int((plat == p).sum()), "mape_ml": round(float(ape_ml[plat == p].mean()) * 100, 1),
                              "mape_group_median": round(float(ape_base[plat == p].mean()) * 100, 1)}
                          for p in sorted(set(plat))}
    old = d.loc[train, "value_residual_pct"] if "value_residual_pct" in d else pd.Series(dtype=float)
    has = old.notna().values
    if has.any():   # the branch's Ridge model, judged on the rows where it exists
        ridge = price[has] / (1 + old.values[has] / 100)
        rep.update(n_ridge=int(has.sum()),
                   mape_ridge_same_rows=round(float(np.mean(np.abs(ridge - price[has]) / price[has])) * 100, 1),
                   mape_ml_same_rows=round(float(np.mean(np.abs(ml[has] - price[has]) / price[has])) * 100, 1))
    REPORT["price"] = rep
    if save:
        MODELS.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": full, "columns": cols}, MODELS / "price_model.joblib")
    return d


def enrich(d, save=True):
    """Area estimate + fair price for every row; d needs duplicate_of (optional), is_shared is added here."""
    d = add_fair_price(add_area(mark_shared(d)), save=save)
    print("price model:", json.dumps(REPORT, ensure_ascii=False))
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="re-fit on the prepared file and print CV errors")
    ap.parse_args()
    from src.recsys.prepare import OUT
    enrich(pd.read_csv(OUT, low_memory=False), save=False)


if __name__ == "__main__":
    main()
