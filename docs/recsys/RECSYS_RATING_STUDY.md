# Recommender — Rating Study (provisional, model-rated)

Status: **provisional.** All ratings below were given by Claude (the assistant), as a stand-in for human ratings, from the listing text only
(title, description, price, area, district, distance fields). No photos, no site visits. They are *not* user feedback.

## Setup
- Ratings 1–5: 5 = fits the persona's constraints and the data looks trustworthy; 3 = acceptable but doubtful (unknown area, suspicious distance,
  price at the budget ceiling); 1–2 = clearly wrong (too far from the target, per-person/dormitory/stale ad, implausible data).
- **Study A (head-to-head, 10 personas, 100 ratings):** top-5 of the *price-only baseline* ("cheapest first") vs the *default* score
  (0.30 price-fit + 0.25 value + 0.25 distance + 0.20 amenities, with the typical-price rule) for every second persona of `src/recsys/evaluate.py`.
  File: `data/recsys_eval_labels_v2.csv` (columns `persona, config, rank, listing_id, rating_1_5`).
- **Study B (default only, 5 other personas, 25 ratings):** `data/recsys_eval_labels.csv` (the file the evaluation script re-uses; existing ratings are now preserved when it is re-run).
- Caveat on blindness: I knew which list came from which configuration while rating, and I also wrote the system. Treat any gap as an upper bound.

## Results
| | mean rating | rated ≥ 4 | rated ≥ 3 | rated ≤ 2 |
|---|---|---|---|---|
| Baseline (cheapest first), 50 ratings | 3.12 | 28% | 86% | 14% |
| Default score, same 10 personas, 50 ratings | **3.78** | **72%** | 90% | 10% |
| Default score, all 15 personas, 75 ratings | 3.69 | 65% | – | – |

Per persona, default minus baseline (mean rating): the default wins on **10 of 10** personas (ties 0, losses 0);
mean difference **+0.66**, bootstrap 95% interval over personas **[+0.42, +0.94]** (n = 10, so the interval is rough).
Largest gains: SV HOU +1.6, SV AJC +1.2, Studio Ba Đình +0.8. Smallest: Cần thang máy +0.2, SV NEU +0.2.

## What the ratings say
1. The score beats "cheapest first" mainly by dropping rooms that are far from the target university (baseline often returned Lĩnh Nam / Hoàng Mai rooms 4–5 km away)
   and by preferring listings with filled-in area and amenities.
2. Remaining weak spots seen while rating:
   - A "Ký túc xá" (dormitory) listing keeps appearing for the elevator and high-budget personas (rated 2): likely not a normal rental, and its `pet_allowed`/amenity flags look wrong.
   - Some distances to universities look wrong (ward-level coordinates), e.g. Trường Chinh listed 0.27 km from NEU.
   - "Ngân sách cao" (12M budget) still gets 3.4–5.5M rooms: the score is anchored on the typical price, not the stated budget, so a high budget does not pull results up-market.
   - Listings with unknown area still enter the top-5 when the persona asked for a minimum area (rated 3).
   - Stale ads ("đầu tháng 7 trống phòng") and near-duplicate units in the same building are not filtered.
3. Ratings of identical listings were kept consistent across configurations (e.g. the same room is not rated differently for baseline and default).

## Decisions
- The default weights 30/25/25/20 are **not changed**: there is no evidence yet for a better set. Learning weights is still blocked on real human ratings.
- Next useful steps (not done): treat dormitory/"KTX" listings as non-rentals; let the budget influence the typical-price anchor; mark stale ads; then have a human re-rate
  `data/recsys_eval_labels_v2.csv` (fill a new `rating_human` column) and compare with these numbers.

## Reproduce
```bash
python -m src.recsys.evaluate            # regenerates docs/RECSYS_EVAL.md and the 5-persona label sheet; keeps existing ratings
python -m pytest tests -q
```
