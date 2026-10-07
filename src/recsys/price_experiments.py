"""Price-prediction experiments for the report (docs/PLAN_PIVOT.md, part A).

    python -m src.recsys.price_experiments      # ~10-20 min -> docs/report_numbers.json["price_experiments"]
                                                #               data/interim/price_oof.csv (out-of-fold predictions)

All models are scored on the same five grouped folds as price_model.py (one poster, or one ~50 m cell, never on both
sides), on the log of the asking rent, and compared with a cluster bootstrap over those groups.
  A1 noisy labels: content-based flags (price ranges, per-person/bed prices, sublets, size/type mismatches); train on all
     vs train on clean, both scored on the same clean test rows. Flags never look at the price itself.
  A2 nine models plus the median baseline; A3 nested random search for the gradient-boosted model;
  A4 permutation importance and partial dependence; A5 ablation of feature groups; A6 leave-one-source-out;
  A7 quantile regression (10/50/90%) and the coverage of its 80% interval; A8 paired differences with intervals.
"""
import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import ExtraTreesRegressor, GradientBoostingRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.inspection import partial_dependence
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import GroupKFold, RandomizedSearchCV
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from src.clean.text_clean import ascii_fold
from src.recsys import price_model as pm
from src.recsys.prepare import OUT as DATA

ROOT = Path(__file__).resolve().parents[2]
NUMS = ROOT / "docs/report_numbers.json"
OOF = ROOT / "data/interim/price_oof.csv"
CATS, NUMERIC = pm.CATS, pm.AMENITIES + pm.DIST + ["area_m2"]
GROUPS = {"Area": ["area_m2"], "Room type": ["house_type"], "District": ["district"], "Source": ["platform"],
          "Distances": pm.DIST, "Amenities": pm.AMENITIES}
SEED = 0

# ---------------------------------------------------------------- A1: content-based flags of a price that is not a room's rent
FLAGS = {
    "price range": re.compile(r"(?<!\w)\d[\d.,]*\s*(?:tr|trieu|k|m)?\s*(?:-|–|~|den)\s*\d[\d.,]*\s*(?:tr|trieu|k|m)\b|\btu\s+\d[\d.,]*\s*(?:tr|trieu|k)"),
    "per person or bed": re.compile(r"/\s*(?:nguoi|ng|giuong|bed|slot)\b|\b1\s*nguoi\b|\bo ghep\b|\bghep\b|homestay|sleep ?box|\bktx\b|ky tuc"),
    "sublet": re.compile(r"\bpass\b|nhuong|sang lai"),
}
WHOLE_HOUSE_WORDS = re.compile(r"nguyen can|nha rieng|ca nha|nha \d+ tang")


def noise_flags(t):
    """Boolean frame of reasons a listed price may not be one room's monthly rent (text and type only, never the price).
    Titles only: descriptions are full of utility prices ("điện 3.5k-4k") that look like price ranges."""
    text = t.title.fillna("").map(lambda s: re.sub(r"tang\s*\d+", " ", (ascii_fold(s) or "").lower()))   # "tầng 4 - 4,1 tr"
    f = pd.DataFrame({k: text.str.contains(rx) for k, rx in FLAGS.items()}, index=t.index)
    room_like = t.house_type.isin(["Phòng trọ", "Studio"])
    f["size or type mismatch"] = (room_like & (t.area_m2 >= 60)) | (room_like & t.title.fillna("").map(
        lambda s: bool(WHOLE_HOUSE_WORDS.search((ascii_fold(s) or "").lower()))))
    return f


# ---------------------------------------------------------------- models
text_of = pm.text_of   # digits removed: 52% of titles state the asking price


def tab_frame(t):
    X = t[CATS + NUMERIC].copy()
    for c in CATS:
        X[c] = X[c].fillna("?").astype(str)
    return X


def linear_prep():
    return ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=10), CATS),
        ("num", make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler()), NUMERIC)])


def tree_prep(impute=False):
    num = make_pipeline(SimpleImputer(strategy="median", add_indicator=True)) if impute else "passthrough"
    return ColumnTransformer([("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), CATS),
                              ("num", num, NUMERIC)])


class TextRidge:
    """Ridge on one-hot/scaled tabular features plus a word+character TF-IDF of the text (fit in-fold)."""

    def fit(self, X, y, text):
        self.prep = linear_prep().fit(X)
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, max_features=20_000, sublinear_tf=True)
        self.m = RidgeCV(alphas=np.logspace(-1, 3, 13)).fit(sparse.hstack([self.prep.transform(X), self.vec.fit_transform(text)]).tocsr(), y)
        return self

    def predict(self, X, text):
        return self.m.predict(sparse.hstack([self.prep.transform(X), self.vec.transform(text)]).tocsr())


def models():
    """name -> (factory, uses_text, input kind). 'hgb' uses the category-dtype frame of price_model."""
    return {
        "Ridge regression": (lambda: make_pipeline(linear_prep(), RidgeCV(alphas=np.logspace(-2, 3, 12))), False, "tab"),
        "k-nearest neighbours (k = 15)": (lambda: make_pipeline(linear_prep(), KNeighborsRegressor(15, weights="distance")), False, "tab"),
        "Random forest": (lambda: make_pipeline(tree_prep(), RandomForestRegressor(300, min_samples_leaf=3, max_features=0.5,
                                                                                    n_jobs=-1, random_state=SEED)), False, "tab"),
        "Extra trees": (lambda: make_pipeline(tree_prep(), ExtraTreesRegressor(300, min_samples_leaf=3, max_features=0.5,
                                                                               n_jobs=-1, random_state=SEED)), False, "tab"),
        "Gradient boosting (classic)": (lambda: make_pipeline(tree_prep(impute=True), GradientBoostingRegressor(
            n_estimators=400, learning_rate=0.05, max_depth=3, subsample=0.8, random_state=SEED)), False, "tab"),
        "Histogram gradient boosting": (pm._model, False, "hgb"),
        "Ridge + text": (TextRidge, True, "tab"),
        "Histogram gradient boosting + text": (pm.TextBoost, True, "hgb"),
    }


# ---------------------------------------------------------------- evaluation helpers
def oof_predict(factory, uses_text, kind, t, y, folds, text, rows=None):
    """Out-of-fold log predictions; `rows` (boolean) restricts the TRAINING rows of every fold (A1). Predictions are clipped
    to the range of rents seen in training (a linear model otherwise extrapolates wildly for a few extreme rooms)."""
    X = pm._X(t, CATS + NUMERIC) if kind == "hgb" else tab_frame(t)
    pred = np.full(len(t), np.nan)
    for tr, te in folds:
        if rows is not None:
            tr = tr[rows[tr]]
        m = factory()
        if uses_text:
            m.fit(X.iloc[tr], y[tr], text.iloc[tr])
            pred[te] = m.predict(X.iloc[te], text.iloc[te])
        else:
            m.fit(X.iloc[tr], y[tr])
            pred[te] = m.predict(X.iloc[te])
        pred[te] = np.clip(pred[te], y[tr].min(), y[tr].max())
    return pred


def metrics(logpred, y, groups, ref_ape=None, mask=None):
    m = np.ones(len(y), bool) if mask is None else mask
    price, pred = np.exp(y[m]), np.exp(logpred[m])
    ape = np.abs(pred - price) / price * 100
    resid = logpred[m] - y[m]
    out = {"n": int(m.sum()), "mape": round(float(ape.mean()), 2), "median_ape": round(float(np.median(ape)), 1),
           "mae_m_vnd": round(float(np.mean(np.abs(pred - price))) / 1e6, 3),
           "rmse_log": round(float(np.sqrt(np.mean(resid ** 2))), 4),
           "r2_log": round(float(1 - np.sum(resid ** 2) / np.sum((y[m] - y[m].mean()) ** 2)), 3),
           "within_15": round(float((ape <= 15).mean() * 100), 1), "within_25": round(float((ape <= 25).mean() * 100), 1)}
    ci = pm.cluster_ci(ape, ref_ape[m] if ref_ape is not None else ape, groups[m])
    out["ci95_mape"] = [round(v, 2) for v in ci["a"]]
    if ref_ape is not None:
        out["diff_vs_ref"] = round(float(ape.mean() - ref_ape[m].mean()), 2)
        out["ci95_diff_vs_ref"] = [round(v, 2) for v in ci["diff"]]
    return out, ape


def ape_of(logpred, y):
    return np.abs(np.exp(logpred) - np.exp(y)) / np.exp(y) * 100


# ---------------------------------------------------------------- experiments
def run():
    started = time.time()
    d = pd.read_csv(DATA, low_memory=False, dtype={"contact_phone": str, "listing_id": str})
    t = d[pm._train_rows(d)].reset_index(drop=True)
    y = np.log(t.price_vnd.values)
    groups = pm.cv_groups(t)
    folds = list(pm._splits(len(t), groups))
    text = text_of(t)
    res = {"n_rooms": int(len(t)), "folds": "GroupKFold(5) by phone hash, else ~50 m cell (same as price_model)",
           "target": "log asking rent; metrics on the rent itself"}

    base = pm._group_median_oof((t.house_type.fillna("") + "|" + t.district.fillna("")).values, y, groups)
    base_ape = ape_of(base, y)

    # A2 + A8: all models, paired with the baseline
    preds, table = {"Median of room type × district": base}, {}
    table["Median of room type × district"], _ = metrics(base, y, groups)
    for name, (factory, uses_text, kind) in models().items():
        t0 = time.time()
        preds[name] = oof_predict(factory, uses_text, kind, t, y, folds, text)
        table[name], _ = metrics(preds[name], y, groups, base_ape)
        table[name]["seconds"] = round(time.time() - t0, 1)
        print(f"  {name}: MAPE {table[name]['mape']}  ({table[name]['seconds']} s)")

    # A3: nested random search for histogram gradient boosting (inner: GroupKFold(3) on the outer training part)
    space = {"learning_rate": [0.02, 0.05, 0.1], "max_iter": [200, 400, 800], "max_leaf_nodes": [15, 31, 63],
             "min_samples_leaf": [10, 20, 40], "l2_regularization": [0.0, 0.5, 1.0, 3.0]}
    X = pm._X(t, CATS + NUMERIC)
    tuned, chosen = np.full(len(t), np.nan), []
    for tr, te in folds:
        search = RandomizedSearchCV(HistGradientBoostingRegressor(categorical_features="from_dtype", random_state=SEED),
                                    space, n_iter=16, cv=GroupKFold(3), scoring="neg_mean_absolute_error",
                                    random_state=SEED, n_jobs=-1)
        search.fit(X.iloc[tr], y[tr], groups=groups[tr])
        tuned[te] = search.predict(X.iloc[te])
        chosen.append(search.best_params_)
    preds["Histogram gradient boosting, tuned"] = tuned
    table["Histogram gradient boosting, tuned"], _ = metrics(tuned, y, groups, base_ape)
    res["tuning"] = {"space": space, "n_iter": 16, "inner_cv": "GroupKFold(3) on each outer training part",
                     "best_params_per_fold": chosen}
    print("  tuned HGB:", table["Histogram gradient boosting, tuned"]["mape"])

    # fixed, a-priori blend of the best tree model and the best linear model with text
    blend = (preds["Histogram gradient boosting + text"] + preds["Ridge + text"]) / 2
    preds["Average of HGB + text and Ridge + text"] = blend
    table["Average of HGB + text and Ridge + text"], _ = metrics(blend, y, groups, base_ape)

    best = min((k for k in table if k != "Median of room type × district"), key=lambda k: table[k]["mape"])
    best_ape = ape_of(preds[best], y)
    for k in table:
        if k != best:
            m_ = metrics(preds[k], y, groups, best_ape)[0]
            table[k]["diff_vs_best"], table[k]["ci95_diff_vs_best"] = m_["diff_vs_ref"], m_["ci95_diff_vs_ref"]
    res["models"], res["best_model"] = table, best

    # A1: noisy labels
    flags = noise_flags(t)
    noisy = flags.any(axis=1).values
    clean = ~noisy
    hgb = models()["Histogram gradient boosting"]
    on_clean = oof_predict(*hgb, t, y, folds, text, rows=clean)
    res["noise"] = {
        "flagged": int(noisy.sum()), "share": round(float(noisy.mean()), 3),
        "by_reason": {k: int(v) for k, v in flags.sum().items()},
        "mape_on_flagged_rows": round(float(ape_of(preds["Histogram gradient boosting"], y)[noisy].mean()), 1),
        "mape_on_clean_rows": round(float(ape_of(preds["Histogram gradient boosting"], y)[clean].mean()), 1),
        "train_all_test_clean": metrics(preds["Histogram gradient boosting"], y, groups, mask=clean)[0],
        "train_clean_test_clean": metrics(on_clean, y, groups, ape_of(preds["Histogram gradient boosting"], y), mask=clean)[0],
        "baseline_test_clean": metrics(base, y, groups, mask=clean)[0],
    }
    print("  noise:", res["noise"]["flagged"], "flagged")

    # A4: permutation importance (grouped columns, 5 repeats per fold) and partial dependence
    rng = np.random.default_rng(SEED)
    imp = {g: [] for g in GROUPS}
    fold_models = []
    for tr, te in folds:
        m = pm._model().fit(X.iloc[tr], y[tr])
        fold_models.append(m)
        ref = ape_of(m.predict(X.iloc[te]), y[te]).mean()
        for g, cols in GROUPS.items():
            for _ in range(5):
                Xp = X.iloc[te].copy()
                perm = rng.permutation(len(te))
                Xp[cols] = Xp[cols].iloc[perm].values
                imp[g].append(ape_of(m.predict(Xp), y[te]).mean() - ref)
    res["permutation_importance"] = {g: {"mean_increase_mape": round(float(np.mean(v)), 2),
                                         "sd": round(float(np.std(v)), 2)} for g, v in imp.items()}
    full = pm._model().fit(X, y)
    pdp = {}
    for col, grid in [("area_m2", np.arange(10, 81, 5)), ("distance_to_center_km", np.arange(0, 20.1, 1.0))]:
        r = partial_dependence(full, X, [col], custom_values={col: grid}, kind="average", method="brute")
        pdp[col] = {"grid": [float(v) for v in grid], "rent_m_vnd": [round(float(np.exp(v)) / 1e6, 3) for v in r["average"][0]]}
    res["partial_dependence"] = pdp

    # A5: ablation (drop one group at a time)
    abl = {}
    hgb_ape = ape_of(preds["Histogram gradient boosting"], y)
    for g, cols in GROUPS.items():
        keep = [c for c in CATS + NUMERIC if c not in cols]
        p = np.full(len(t), np.nan)
        Xk = pm._X(t, keep)
        for tr, te in folds:
            p[te] = pm._model().fit(Xk.iloc[tr], y[tr]).predict(Xk.iloc[te])
        abl[g] = metrics(p, y, groups, hgb_ape)[0]
    res["ablation"] = abl

    # A6: leave one source out (the source feature is dropped; the baseline uses only the other sources too)
    loso = {}
    cols = [c for c in CATS + NUMERIC if c != "platform"]
    Xs = pm._X(t, cols)
    key = (t.house_type.fillna("") + "|" + t.district.fillna("")).values
    for src in t.platform.value_counts().index:
        te = (t.platform == src).values
        if te.sum() < 50:
            continue
        p = pm._model().fit(Xs[~te], y[~te]).predict(Xs[te])
        med = pd.Series(y[~te]).groupby(key[~te]).median()
        b = pd.Series(key[te]).map(med).fillna(np.median(y[~te])).values
        loso[src] = {"n": int(te.sum()), "mape_model": round(float(ape_of(p, y[te]).mean()), 1),
                     "mape_baseline": round(float(ape_of(b, y[te]).mean()), 1),
                     "mape_in_cv": round(float(hgb_ape[te].mean()), 1)}
    res["leave_one_source_out"] = loso

    # A7: quantile regression, 80% interval
    q = {}
    for a in (0.05, 0.1, 0.5, 0.9, 0.95):
        p = np.full(len(t), np.nan)
        for tr, te in folds:
            p[te] = HistGradientBoostingRegressor(loss="quantile", quantile=a, categorical_features="from_dtype", max_iter=400,
                                                  learning_rate=0.05, l2_regularization=1.0, random_state=SEED).fit(
                X.iloc[tr], y[tr]).predict(X.iloc[te])
        q[a] = p
    inside = (y >= q[0.1]) & (y <= q[0.9])
    stated = t.area_m2.notna().values
    res["quantile"] = {
        "coverage_80": round(float(inside.mean() * 100), 1),
        "coverage_90": round(float(((y >= q[0.05]) & (y <= q[0.95])).mean() * 100), 1),
        "coverage_80_area_stated": round(float(inside[stated].mean() * 100), 1),
        "coverage_80_area_missing": round(float(inside[~stated].mean() * 100), 1),
        "median_width_ratio": round(float(np.median(np.exp(q[0.9] - q[0.1]))), 2),
        "below_interval": round(float((y < q[0.1]).mean() * 100), 1),
        "above_interval": round(float((y > q[0.9]).mean() * 100), 1),
        "median_model_mape": metrics(q[0.5], y, groups, base_ape)[0]["mape"],
    }
    res["seconds"] = round(time.time() - started)

    OOF.parent.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame({"listing_id": t.listing_id, "price_vnd": t.price_vnd, "noisy": noisy,
                        **{f"pred_{k}": np.exp(v) for k, v in preds.items()},
                        "q10": np.exp(q[0.1]), "q50": np.exp(q[0.5]), "q90": np.exp(q[0.9])})
    out.to_csv(OOF, index=False, encoding="utf-8-sig")
    nums = json.loads(NUMS.read_text(encoding="utf-8")) if NUMS.exists() else {}
    nums["price_experiments"] = res
    NUMS.write_text(json.dumps(nums, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"wrote price_experiments to {NUMS} and {OOF} in {res['seconds']} s")
    return res


if __name__ == "__main__":
    run()
