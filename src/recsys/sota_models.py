"""State-of-the-art gradient-boosting libraries on the same grouped folds as the other price models.

LightGBM, XGBoost and CatBoost, with default tree settings (400 trees, learning rate 0.05), on the tabular features and on the
tabular features plus 64 SVD components of the digit-free text (same text pipeline as price_model.TextBoost). Everything else is
identical to price_experiments: same rooms, same folds, predictions clipped to the training range, cluster-bootstrap intervals.
Writes docs/report_numbers.json["sota_models"].

    python -m src.recsys.sota_models
"""
import json
import time
import warnings

import numpy as np
import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

from src.recsys import price_experiments as E
from src.recsys import price_model as pm

warnings.filterwarnings("ignore")
N_TREES, LR, SEED = 400, 0.05, 0


def _lightgbm():
    import lightgbm
    return lightgbm.LGBMRegressor(n_estimators=N_TREES, learning_rate=LR, random_state=SEED, verbose=-1, n_jobs=-1)


def _xgboost():
    import xgboost
    return xgboost.XGBRegressor(n_estimators=N_TREES, learning_rate=LR, random_state=SEED, enable_categorical=True,
                                tree_method="hist", n_jobs=-1)


def _catboost():
    import catboost
    return catboost.CatBoostRegressor(iterations=N_TREES, learning_rate=LR, random_seed=SEED, verbose=0, thread_count=-1)


def _prep(X, name):
    """CatBoost wants string categories; LightGBM and XGBoost use the pandas category dtype directly."""
    if name != "CatBoost":
        return X
    X = X.copy()
    for c in E.CATS:
        X[c] = X[c].astype(object).where(X[c].notna(), "NA").astype(str)
    return X


def _fit(model, name, X, y):
    if name == "CatBoost":
        return model.fit(_prep(X, name), y, cat_features=list(E.CATS))
    return model.fit(X, y)


class Tab:
    def __init__(self, name, make):
        self.name, self.make = name, make

    def fit(self, X, y):
        self.m = _fit(self.make(), self.name, X, y)
        return self

    def predict(self, X):
        return self.m.predict(_prep(X, self.name))


class WithText(Tab):
    def fit(self, X, y, text):
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, max_features=50_000, sublinear_tf=True)
        tf = self.vec.fit_transform(text)
        self.svd = TruncatedSVD(min(64, tf.shape[1] - 1), random_state=SEED)
        self.m = _fit(self.make(), self.name, self._join(X, self.svd.fit_transform(tf)), y)
        return self

    @staticmethod
    def _join(X, Z):
        return pd.concat([X.reset_index(drop=True), pd.DataFrame(Z, columns=[f"svd{i}" for i in range(Z.shape[1])])], axis=1)

    def predict(self, X, text):
        return self.m.predict(_prep(self._join(X, self.svd.transform(self.vec.transform(text))), self.name))


LIBS = {"LightGBM": _lightgbm, "XGBoost": _xgboost, "CatBoost": _catboost}


def run():
    d = pd.read_csv(E.DATA, low_memory=False, dtype={"contact_phone": str, "listing_id": str})
    t = d[pm._train_rows(d)].reset_index(drop=True)
    y = np.log(t.price_vnd.values)
    groups = pm.cv_groups(t)
    folds = list(pm._splits(len(t), groups))
    text = E.text_of(t)
    base = pm._group_median_oof((t.house_type.fillna("") + "|" + t.district.fillna("")).values, y, groups)

    ref_name = "Histogram gradient boosting + text"
    ref = E.oof_predict(*E.models()[ref_name], t, y, folds, text)
    ref_ape = E.ape_of(ref, y)
    res = {"settings": f"{N_TREES} trees, learning rate {LR}, otherwise library defaults; same folds, rooms and text pipeline as the other models",
           "reference": {ref_name: E.metrics(ref, y, groups, E.ape_of(base, y))[0]}}
    for lib, make in LIBS.items():
        for text_on in (False, True):
            name = f"{lib} + text" if text_on else lib
            t0 = time.time()
            cls = WithText if text_on else Tab
            pred = E.oof_predict(lambda lib=lib, make=make, cls=cls: cls(lib, make), text_on, "hgb", t, y, folds, text)
            m = E.metrics(pred, y, groups, ref_ape)[0]  # difference is relative to the final model (HGB + text)
            m["seconds"] = round(time.time() - t0, 1)
            res[name] = m
            print(f"  {name}: MAPE {m['mape']} (diff vs final {m['diff_vs_ref']}, {m['ci95_diff_vs_ref']})  {m['seconds']} s")
    nums = json.loads(E.NUMS.read_text(encoding="utf-8"))
    nums["sota_models"] = res
    E.NUMS.write_text(json.dumps(nums, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("wrote sota_models to", E.NUMS)


if __name__ == "__main__":
    run()
