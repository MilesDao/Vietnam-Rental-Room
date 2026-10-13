# Recommender — working notes (condensed)

Merges the earlier `RECSYS_REPORT`, `RECSYS_UPDATE_REPORT`, `RECSYS_PLAN` and `RECSYS_RATING_STUDY` (originals in `docs/archive/recsys/`).
The final write-up is `RECSYS_FINAL_REPORT.md`; the tables are in `RECSYS_EVAL.md`. All ratings below are **model-assigned (Claude)**, from listing text
only — useful for finding bugs, not evidence of quality for real users.

## What was built
| Piece | Files | Notes |
|---|---|---|
| Recommender | `recommend.py` | Hard filters (budget, district, min area, amenities, university + max km, metro km, house type), then score = 0.30 price + 0.25 value + 0.25 distance + 0.20 amenities. Never outputs contact data. |
| Cross-platform dedup | `sample_schema.mark_duplicates(cross_platform=True)` | Price ±5%, area ±1 m², same title or house/alley address, complete linkage. 15,861 → 13,673 listings (~2,000 were Facebook). |
| Missing area | `recommend.impute_area()` | `area_est` + `area_imputed`; holdout MAE 7.8 m² (type × price) vs 10.5 m² (global median). Never used for `--min-area`. Missing area: Rencity 100%, Facebook 74%, Chotot 37%, rest ≤ 2%. |
| App | `app.py` | Streamlit + Folium; sidebar mirrors the CLI; 22 universities and 20 metro stations on the map; "© OpenStreetMap contributors" in the footer. |
| Evaluation | `evaluate.py` | 20 personas × 5 weight settings, top-10 → `RECSYS_EVAL.md`. |
| Geo repair | `regeocode_fallback.py`, `ref_points.py` | See below. |

## Bugs found by evaluating, and the fixes
1. **Shared-room / per-bed ads swamped the top-10** (2.8% of data, 42% of top-10): price is per bed, area is the whole room. Excluded by default
   (`SHARED_RE`, `--include-shared`); keyword heuristic, now ~4.2% flagged, a few variants still slip through.
2. **Ranking rewarded the cheapest ad** (`1 − price/budget`). Now `price_score()`: 1 at the typical price of the house type × district, falling off for
   suspiciously cheap rooms. Mean price/budget of the top-10 went 0.47 → 0.76.
3. **Fake fallback coordinate**: 538 Phongtro123 rows (3.4%) sat on one point (21.028511, 105.804817) although their addresses named 35 different wards, so the "UTC" persona
   saw rooms 30 km away at "0.11 km". Fixed at the root: each distinct ward geocoded once with the cached Nominatim client (24 of 35 resolved, 428 rows recovered;
   the rest are outside Hanoi or unresolved and keep NaN). `null_fallback_geo()` stays as a guard.
4. **Near-duplicate units in one building** are not merged (they can be different rooms); `--per-building N` shows the best one per building instead.
5. The "dormitory with `pet_allowed`" listing was checked and its flag is correct in the source; it was left unchanged.

## Self-rated quality (5 personas, top-5, mean of 1–5)
| Stage | Mean | ≥ 4 |
|---|---|---|
| Initial | 2.60 | 24% |
| Shared ads removed + fallback geo nulled | 3.16 | 28% |
| New price score (geo repair left the top-5 unchanged) | 3.52 | 52% |

Head-to-head over 10 personas (50 ratings each): default 3.78 vs cheapest-first 3.12; default wins 10/10, mean difference +0.66
(bootstrap 95% interval over personas +0.42 to +0.94; n = 10, rough). The raters knew which list was which and wrote the system, so treat the gap as an upper bound.
Weights 30/25/25/20 were not changed: "equal 25 each" is indistinguishable from them.

## Still open
- Coordinates are ward-level for many rooms (hundreds share one centroid), so some distances are approximate; many `ward`/`district` values disagree with the address text.
  Proper fix: a 2025 ward crosswalk in the unified-dataset pipeline.
- `value_residual_pct` was not recomputed for the repaired rows.
- A high budget (12 M) still returns 3.4–5.5 M rooms: the score is anchored on the typical price, not the budget.
- Unknown-area rooms still enter the top-5 when a minimum area is asked; stale ads ("đầu tháng 7 trống phòng") are not filtered; "KTX" listings could be treated as non-rentals.
- A human must re-rate `data/recsys_eval_labels_v2.csv` (new `rating_human` column) before anything is learned from ratings.
- Not done from the old plan: other cities (Hanoi only), human feedback for weight learning (done later with AI votes, see the final report).

## Reproduce
```bash
python -m src.recsys.regeocode_fallback    # ~35 Nominatim requests, cached
python -m src.recsys.prepare               # dedup, area, price model
python -m src.recsys.evaluate              # keeps existing ratings
python -m pytest tests -q
```
