"""Simulation study of the learned ranker with simulated users (docs/PLAN_PIVOT.md, part C).

    python -m src.recsys.simulate_users      # ~2 min -> docs/report_numbers.json["simulation"]

NOT a user study. Simulated users have known, randomly drawn preferences over five signals (price fit, value, closeness,
amenities, not a sublet) plus noise; each rates 20 rooms shown in RANDOM order (no position bias) for 2 of 10 search
scenarios. The votes go through the real pipeline (feedback.log -> ltr.labelled -> ltr.evaluate, grouped by user).
Because the users are linear in the same signals the ranker uses, the study can only answer: does the method recover
known preferences, and how many votes does it need? It cannot show that real renters would prefer its rankings.
Two conditions: similar users (Dirichlet concentration 50) and diverse users (concentration 5).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.recsys import feedback, ltr
from src.recsys.recommend import load, recommend

ROOT = Path(__file__).resolve().parents[2]
NUMS = ROOT / "docs/report_numbers.json"
SIGNALS = ["s_price", "s_value", "s_dist", "s_amenity", "q_not_sublet"]
BASE_PREF = np.array([0.30, 0.15, 0.30, 0.10, 0.15])   # average simulated taste; individual tastes vary around it
NOISE_SD, LIKE_QUANTILE, ROOMS, USERS, SCENARIOS_PER_USER = 0.10, 0.35, 20, 40, 2
SCENARIOS = [
    ("Student near NEU, up to 3 M", dict(budget=3e6, university="NEU", max_uni_km=3)),
    ("Student near VNU, up to 4 M, air conditioning", dict(budget=4e6, university="VNU", max_uni_km=3, need=["air_conditioner"])),
    ("Worker in Cầu Giấy, up to 5 M, at least 20 m²", dict(budget=5e6, districts=["Cầu Giấy"], min_area=20)),
    ("Studio in Đống Đa, up to 6 M", dict(budget=6e6, districts=["Đống Đa"], house_type="Studio")),
    ("Student in Hà Đông, up to 3.5 M", dict(budget=3.5e6, districts=["Hà Đông"])),
    ("Couple in Thanh Xuân, up to 5 M, at least 25 m²", dict(budget=5e6, districts=["Thanh Xuân"], min_area=25)),
    ("High budget with a lift, up to 10 M", dict(budget=10e6, need=["elevator"])),
    ("Student near UTC, up to 3.5 M", dict(budget=3.5e6, university="UTC", max_uni_km=3)),
    ("Hoàng Mai with a washing machine, up to 3.5 M", dict(budget=3.5e6, districts=["Hoàng Mai"], need=["washing_machine"])),
    ("Ba Đình or Tây Hồ, up to 7 M", dict(budget=7e6, districts=["Ba Đình", "Tây Hồ"])),
]


def pools(d):
    """Candidate rooms of each scenario after the hard filters (the ranking order is not used)."""
    out = {}
    for name, p in SCENARIOS:
        r = recommend(d, p["budget"], p.get("districts", ()), p.get("min_area"), p.get("need", ()), p.get("university"),
                      p.get("max_uni_km"), None, p.get("house_type"), top=10 ** 6, per_building=0, ranker="hand")
        out[name] = r.reset_index(drop=True)
    return out


def simulate(pool_of, concentration, db, seed=0):
    """Write the simulated users' impressions and votes to `db`; return their true preference vectors."""
    rng = np.random.default_rng(seed)
    Path(db).unlink(missing_ok=True)
    names = list(pool_of)
    prefs = {}
    for u in range(USERS):
        w = rng.dirichlet(concentration * BASE_PREF / BASE_PREF.sum())
        session = f"sim-{u:02d}"
        prefs[session] = w
        for name in rng.choice(names, SCENARIOS_PER_USER, replace=False):
            pool = pool_of[name]
            rows = pool.iloc[rng.choice(len(pool), min(ROOMS, len(pool)), replace=False)].copy()
            util = rows[SIGNALS].to_numpy(float) @ w + rng.normal(0, NOISE_SD, len(rows))
            rows["rank"] = np.arange(1, len(rows) + 1)          # shown in random order
            rows["score"] = 0.0
            feedback.log(session, name, rows, "impression", db=db)
            liked = util > np.quantile(util, LIKE_QUANTILE)
            feedback.log(session, name, rows[liked], "up", db=db)
            feedback.log(session, name, rows[~liked], "down", db=db)
    return prefs


def condition(pool_of, concentration, db, seed=0):
    prefs = simulate(pool_of, concentration, db, seed)
    v = ltr.labelled(feedback.events(db=db))
    rep, weights = ltr.evaluate(v)
    per = ltr.per_search(v)
    boot = {f"learned_minus_{b}": {k: (round(x, 3) if isinstance(x, float) else x) for k, x in ltr.bootstrap_diff(per, "learned", b).items()}
            for b in ("random", "cheapest", "nearest", "price_dist", "hand")}
    true = np.mean(list(prefs.values()), axis=0)
    learned = np.array([weights["price"], weights["value"], weights["distance"], weights["amenity"], weights["q_not_sublet"]])
    curve = []
    rng = np.random.default_rng(seed + 1)
    sessions = v.session.unique()
    for n in (3, 5, 10, 20, 40):
        runs = []
        for _ in range(10 if n < USERS else 1):
            pick = rng.choice(sessions, n, replace=False)
            r, _ = ltr.evaluate(v[v.session.isin(pick)])
            if "learned_cv" in r:
                runs.append((r["learned_cv"]["ndcg@10"] - r["hand"]["ndcg@10"], r["learned_cv"]["ndcg@10"]))
        a = np.array(runs)
        curve.append({"users": n, "votes": int(n * SCENARIOS_PER_USER * ROOMS),
                      "learned_ndcg_mean": round(float(a[:, 1].mean()), 3),
                      "learned_minus_hand_mean": round(float(a[:, 0].mean()), 3),
                      "learned_minus_hand_sd": round(float(a[:, 0].std()), 3), "repeats": len(runs)})
    return {"concentration": concentration, "users": USERS, "votes": int(len(v)), "share_liked": rep["share_up"],
            "report": {k: rep[k] for k in rep if k not in ("note",)}, "bootstrap_over_searches": boot,
            "true_mean_preference": dict(zip(SIGNALS, np.round(true / true.sum(), 3).tolist())),
            "learned_weights_on_same_signals": dict(zip(SIGNALS, np.round(learned / max(learned.sum(), 1e-9), 3).tolist())),
            "weight_recovery_corr": round(float(np.corrcoef(true, learned)[0, 1]), 3),
            "learning_curve": curve}


def main():
    d = load()
    pool_of = pools(d)
    res = {"what": "simulation study, not a user study: simulated users with known linear preferences plus noise",
           "design": {"signals": SIGNALS, "base_preference": BASE_PREF.tolist(), "noise_sd": NOISE_SD,
                      "like_rule": f"liked if utility above the user's {int(LIKE_QUANTILE * 100)}th percentile in that list",
                      "rooms_per_list": ROOMS, "users": USERS, "scenarios_per_user": SCENARIOS_PER_USER,
                      "order": "random (no position bias)", "evaluation": "ltr.evaluate, folds grouped by user"},
           "pool_sizes": {k: int(len(v)) for k, v in pool_of.items()}}
    for label, conc in (("similar_users", 50.0), ("diverse_users", 5.0)):
        res[label] = condition(pool_of, conc, ROOT / f"data/recsys_feedback_sim_{label}.sqlite")
        r = res[label]["report"]
        print(f"{label}: learned {r.get('learned_cv')} hand {r['hand']} nearest {r['nearest_first']} "
              f"recovery corr {res[label]['weight_recovery_corr']}")
    nums = json.loads(NUMS.read_text(encoding="utf-8"))
    nums["simulation"] = res
    NUMS.write_text(json.dumps(nums, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("wrote simulation to", NUMS)


if __name__ == "__main__":
    main()
