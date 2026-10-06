"""Learning to rank from real 👍/👎 feedback (src/recsys/feedback.py).

    python -m src.recsys.ltr            # report; publishes learned weights only if they win

Model: logistic regression (pointwise learning to rank) on the four score parts the user saw plus three
data-quality signals (not a sublet, has a house/alley address, district label agrees with the address).
Its non-negative coefficients, normalised to sum to 1, become the score weights, so the engine stays a
transparent weighted sum. (Hand-set weights give the quality signals weight 0.) Evaluation is grouped cross-validation by session (no user is in both train
and test), comparing NDCG@10 and precision@5 of: learned weights, the hand-set WEIGHTS, and
cheapest-first. Weights are written to data/models/ltr_weights.json only when there are at least
MIN_LABELS votes from MIN_SESSIONS sessions and the learned weights beat the hand-set ones on held-out NDCG;
otherwise any old file is left alone and recommend() keeps using what it has.
"""
import json
import time

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

from src.recsys.feedback import PARTS, events
from src.recsys.recommend import LTR_WEIGHTS, QUALITY, WEIGHTS, load

MIN_LABELS, MIN_SESSIONS = 200, 5
KEYS = ["price", "value", "distance", "amenity"] + QUALITY   # weight names, same order as FEATS
FEATS = PARTS + QUALITY


def labelled(ev):
    """One row per (session, query, listing) the user voted on: label 1 = 👍, 0 = 👎, plus the rank shown.
    The quality parts are not stored with the vote; they are joined from the current data by listing_id."""
    v = ev[ev.action.isin(["up", "down"])].copy()
    v["label"] = (v.action == "up").astype(int)
    if len(v):
        qual = load().set_index("listing_id")[QUALITY]
        v = v.join(qual, on="listing_id")
        v[QUALITY] = v[QUALITY].fillna(1.0)
    return v


def ndcg_at(scores, labels, k=10):
    order = np.argsort(-np.asarray(scores))[:k]
    gains = np.asarray(labels)[order]
    dcg = (gains / np.log2(np.arange(2, len(gains) + 2))).sum()
    ideal = np.sort(np.asarray(labels))[::-1][:k]
    idcg = (ideal / np.log2(np.arange(2, len(ideal) + 2))).sum()
    return dcg / idcg if idcg > 0 else np.nan


def precision_at(scores, labels, k=5):
    order = np.argsort(-np.asarray(scores))[:k]
    return float(np.asarray(labels)[order].mean())


def rank_metrics(v, score_col):
    g = v.groupby(["session", "query"])
    return {"ndcg@10": round(float(np.nanmean([ndcg_at(x[score_col], x.label) for _, x in g])), 3),
            "p@5": round(float(np.mean([precision_at(x[score_col], x.label) for _, x in g])), 3)}


def random_baseline(v, k=10, draws=300, seed=0):
    """Expected NDCG@k and precision@5 of putting each search's rooms in random order (Monte Carlo)."""
    rng = np.random.default_rng(seed)
    rows = []
    for key, g in v.groupby(["session", "query"]):
        y = g.label.to_numpy()
        nd = np.nanmean([ndcg_at(rng.random(len(y)), y, k) for _ in range(draws)])
        pr = float(y.mean())   # exact expectation of precision@5 under a random order
        rows.append((key[0], nd, pr))
    return pd.DataFrame(rows, columns=["search", "ndcg", "p5"])


def weights_from(model):
    """Non-negative logistic coefficients on FEATS, normalised to sum to 1, become the engine weights."""
    w = np.clip(model.coef_[0], 0, None)
    w = w / w.sum() if w.sum() > 0 else np.full(len(w), 1 / len(w))
    return dict(zip(KEYS, np.round(w, 3).tolist()))


def with_baselines(v):
    """Score columns of the fixed orderings. Hand-set weights need no training, so they are scored on every
    search, while the learned weights are scored held-out; the report must say so."""
    v = v.copy()
    v["hand"] = sum(WEIGHTS.get(k, 0) * v[p] for k, p in zip(KEYS, FEATS))
    v["cheapest"] = -v.price_vnd
    v["nearest"] = v.s_dist                     # nearest first (s_dist: 1 = closest in that result list)
    v["price_dist"] = v.s_price + v.s_dist      # price fit + closeness, equal weights
    v["learned"] = np.nan
    return v


def signed_coefficients(v, n_boot=500, seed=0):
    """Standardised logistic coefficients WITH their sign, and a 95% bootstrap interval over searches.
    For the report only: the engine still uses weights_from() (clipped). A near-constant feature
    (q_not_sublet ~ 98% ones) gets an unstable coefficient, which the interval shows."""
    X = v[FEATS].astype(float)
    sd = X.std().replace(0, 1)
    Z = (X - X.mean()) / sd

    def fit(idx):
        y = v.label.iloc[idx]
        if y.nunique() < 2:
            return None
        return LogisticRegression(max_iter=1000).fit(Z.iloc[idx], y).coef_[0]

    full = fit(np.arange(len(v)))
    keys = list(v.groupby(["session", "query"]).indices.values())
    rng = np.random.default_rng(seed)
    boots = [b for b in (fit(np.concatenate([keys[i] for i in rng.integers(0, len(keys), len(keys))]))
                         for _ in range(n_boot)) if b is not None]
    lo, hi = np.percentile(boots, [2.5, 97.5], axis=0)
    return {k: {"coef": round(float(c), 3), "lo": round(float(a), 3), "hi": round(float(b), 3)}
            for k, c, a, b in zip(KEYS, full, lo, hi)}


def evaluate(v):
    """Grouped-CV comparison; returns (report dict, weights fit on all data or None)."""
    v = with_baselines(v)
    n_splits = min(5, v.session.nunique())
    if n_splits >= 2 and v.label.nunique() == 2:
        for tr, te in GroupKFold(n_splits).split(v, groups=v.session):
            if v.label.iloc[tr].nunique() < 2:
                continue
            w = weights_from(LogisticRegression(max_iter=1000).fit(v[FEATS].iloc[tr], v.label.iloc[tr]))
            v.iloc[te, v.columns.get_loc("learned")] = sum(w[k] * v[p].iloc[te] for k, p in zip(KEYS, FEATS))
    rep = {"labels": int(len(v)), "sessions": int(v.session.nunique()), "share_up": round(float(v.label.mean()), 3),
           "hand": rank_metrics(v, "hand"), "cheapest_first": rank_metrics(v, "cheapest"),
           "nearest_first": rank_metrics(v, "nearest"), "price_plus_distance": rank_metrics(v, "price_dist"),
           "note": "hand/nearest/price_plus_distance are scored on all searches; learned_cv is held-out"}
    rnd = random_baseline(v)
    rep["random"] = {"ndcg@10": round(float(rnd.ndcg.mean()), 3), "p@5": round(float(rnd.p5.mean()), 3)}
    if v.learned.notna().all():
        rep["learned_cv"] = rank_metrics(v, "learned")
    full = None
    if v.label.nunique() == 2:
        full = weights_from(LogisticRegression(max_iter=1000).fit(v[FEATS], v.label))
        rep["learned_weights"] = full
        if v.groupby(["session", "query"]).ngroups >= 2:
            rep["coef_std"] = signed_coefficients(v)
    return rep, full


def per_search(v, k=10):
    """NDCG@k per search for hand-set, learned (session-grouped CV), cheapest-first, nearest-first and
    price+distance, one row per search."""
    v = with_baselines(v)
    for tr, te in GroupKFold(min(5, v.session.nunique())).split(v, groups=v.session):
        w = weights_from(LogisticRegression(max_iter=1000).fit(v[FEATS].iloc[tr], v.label.iloc[tr]))
        v.iloc[te, v.columns.get_loc("learned")] = sum(w[kk] * v[p].iloc[te] for kk, p in zip(KEYS, FEATS))
    rows = []
    for key, g in v.groupby(["session", "query"]):
        rows.append({"search": key[0], **{c: ndcg_at(g[c], g.label, k)
                                          for c in ("hand", "learned", "cheapest", "nearest", "price_dist")}})
    per = pd.DataFrame(rows).dropna()
    rnd = random_baseline(v).set_index("search").ndcg
    per["random"] = per.search.map(rnd)
    return per


def bootstrap_diff(per, a="hand", b="learned", n=10_000, seed=0):
    """Paired bootstrap over searches: mean(a - b) and its 95% interval, plus P(a > b) among resamples."""
    d = (per[a] - per[b]).to_numpy()
    rng = np.random.default_rng(seed)
    means = np.array([rng.choice(d, len(d)).mean() for _ in range(n)])
    return {"mean": float(d.mean()), "lo": float(np.percentile(means, 2.5)), "hi": float(np.percentile(means, 97.5)),
            "p_a_better": float((means > 0).mean()), "searches": int(len(d))}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", help="feedback database to learn from (default: real user feedback); e.g. "
                                 "data/recsys_feedback_ai.sqlite for the AI-labelled votes")
    ap.add_argument("--force", action="store_true",
                    help="publish the learned weights as the ML ranker even if they are not shown to beat the "
                         "hand-set ones (the report says so)")
    a = ap.parse_args()
    source = "ai-labelled" if a.db and "ai" in a.db else "user feedback"
    v = labelled(events(db=a.db))
    if v.empty:
        print("no 👍/👎 feedback yet — collect some in the app first; recommend() keeps the hand-set weights")
        return
    rep, w = evaluate(v)
    enough = rep["labels"] >= MIN_LABELS and rep["sessions"] >= MIN_SESSIONS
    wins = "learned_cv" in rep and rep["learned_cv"]["ndcg@10"] > rep["hand"]["ndcg@10"]
    rep["published"] = bool(w and ((enough and wins) or a.force))
    rep["forced"] = bool(a.force and not (enough and wins))
    if rep["published"]:
        LTR_WEIGHTS.parent.mkdir(parents=True, exist_ok=True)
        LTR_WEIGHTS.write_text(json.dumps({"weights": w, "source": source, "forced": rep["forced"], "report": rep,
                                           "trained_at": time.time()}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    if rep["forced"]:
        print("published with --force: the learned ranker is NOT shown to beat the hand-set weights "
              f"(enough data: {enough}, wins on held-out NDCG@10: {wins})")
    elif not rep["published"]:
        print(f"not published: need >= {MIN_LABELS} votes from >= {MIN_SESSIONS} sessions and a held-out win "
              "(or use --force)")


if __name__ == "__main__":
    main()
