# Recommender — Update Report (English)

Date: 2026-10-04 · Scope: everything added or changed for the Hanoi rental recommender, including the
latest geocoding fix. Vietnamese working notes live in `docs/RECSYS_REPORT.md` / `RECSYS_PLAN.md`; evaluation tables in `docs/RECSYS_EVAL.md`.

## 1. Summary
| Area | Result |
|---|---|
| Data | `data/` copied from `origin/unified-crawl-data` (no merge; no existing file overwritten). |
| Recommender | CLI + Streamlit/Folium map app; hard filters + weighted score. |
| Cross-platform dedup | 15,861 → 13,673 listings (2,188 folded; ~2,000 of them Facebook). |
| Missing area | `area_est` + `area_imputed` (holdout MAE 7.8 m² vs 10.5 m² for a global median). |
| Evaluation | 20 personas × 5 weight settings; self-rated top-5 for 5 personas (mean 2.60 → 3.52 out of 5). |
| Bugs found by evaluation | 4 (shared-room ads, per-person homestay prices, cheapness bias, fallback coordinates) — all fixed or mitigated. |
| Tests | 58 pass (`python -m pytest tests -q`). |

## 2. What was built
- `src/recsys/recommend.py` — `load()`, `recommend()`, CLI. Filters: max rent, district, min area, required amenities,
  nearest university (+ max km), max metro km, house type. Score = 0.30 price + 0.25 value (`value_residual_pct`)
  + 0.25 distance (to the chosen university, else to the centre) + 0.20 amenities. Output never contains contact data.
- `src/recsys/app.py` — Streamlit UI (`streamlit run src/recsys/app.py`): sidebar filters, ranked Folium markers with popups
  (price, area — `~` if estimated — and a link), results table, OSM attribution. `streamlit`, `folium`, `streamlit-folium` were added to `requirements.txt`.
- `src/recsys/dedup_unified.py` — cross-platform duplicate marking using `sample_schema.mark_duplicates(cross_platform=True)`
  (same rules as before: price ±5%, area ±1 m², same title or house/alley-level address, complete linkage; one row kept per group).
- `src/recsys/evaluate.py` — persona evaluation → `docs/RECSYS_EVAL.md`, `data/recsys_eval_labels.csv`.
- `src/recsys/regeocode_fallback.py`, `src/recsys/ref_points.py` — geocoding repair (section 4).

## 3. Bugs found by evaluation and how they were handled
1. **Shared-room ads swamped the top-10** (2.8% of data, 42% of the top-10). A shared-room slot is priced per bed but lists the whole room's area, so its
   `value_residual_pct` median was −57% and 60% were labelled "bargain". Now excluded by default (`SHARED_RE`; `--include-shared` / UI checkbox).
   Per-person "homestay / sleep box / 1 người" ads were added to the pattern (now ~4.2% of listings). It is a keyword heuristic: some variants still slip through ("Home stay", "/ng").
2. **Ranking over-rewarded the cheapest ads** (`1 − price/budget`). Replaced by `price_score()`: 1 at the typical price for the same house type × district, falling off for
   suspiciously cheap rooms and only mildly towards the budget. Mean price/budget of the top-10 went 0.47 → 0.76 and top-5 relevance rose (see section 5).
3. **Fallback coordinates** — root cause fixed in section 4.
4. **Duplicates and missing area** — handled by cross-platform dedup and `area_est`.

## 4. Latest change: geocoding root-cause fix
**Problem.** 538 Phongtro123 rows (3.4% of the data) shared one coordinate, (21.028511, 105.804817) — which is also UTC's campus —
although their addresses named 35 different post-2025 wards (Thanh Liệt, Hồng Hà, Trung Giã, Hòa Lạc, ...). Those ward names evidently had no entry in the
pipeline's ward-centroid table, so the rows fell back to one point. They looked "0.11 km from UTC" and "in Đống Đa"; the "SV UTC" persona was shown rooms ~30 km away.

**Fix.** `python -m src.recsys.regeocode_fallback`
- Detects fallback points (≥ 5 distinct address wards at one coordinate) and geocodes each distinct ward once (35 queries) with the project's existing cached
  Nominatim client (≤ 1 request/s, identifying User-Agent, no personal data in queries, responses cached in `data/external/nominatim_cache.sqlite`; 31 requests sent, 4 cache hits).
- 24 of 35 wards resolved, covering 428 of the 538 rows. Unresolved: wards outside Hanoi (Vũng Tàu, Bến Cát, ... — listings that do not belong in a Hanoi dataset) and two Hanoi communes (Lạc Phượng, Xuân Thọ).
  Those rows keep NaN coordinates and distances.
- For resolved rows: ward-centroid lat/lon, the legacy district containing it (point-in-polygon on `data/hanoi_districts.geojson`), and recomputed
  distance-to-centre / nearest metro / nearest university (+ tiers) with the same reference points and method as the original pipeline (`ref_points.py`).
- `dedup_unified.py` now reads `data/unified_hanoi_rentals_geofixed.csv`. The safety net `null_fallback_geo()` in `recommend.load()` stays as a guard (it now finds 0 rows).

**Effect.** 428 listings are usable again for location-based queries (Sóc Sơn 8 → 98 listings, Thạch Thất 5 → 22, Thanh Trì 471 → 548) and no listing sits on the fake UTC point.
The top-5 lists of the five rated personas did not change, because the bad rows had already been excluded by the safety net; the benefit is coverage and correct location filters.
"© OpenStreetMap contributors" is shown in the app and must accompany any published coordinates.

**Not fixed (be aware).**
- Coordinates are ward-level, not rooftop. Hundreds of Phongtro123 rows still share ward centroids (e.g. 353 at one "Phường Từ Liêm" point); distances for them are approximate.
- `value_residual_pct` / `market_value_tier` were **not** recomputed for the repaired rows (the Ridge model lives in the branch-only script and uses district dummies);
  the old wrong district may have slightly biased those values.
- Many `ward`/`district` values come from "nearest old-ward centroid" and disagree with the address text (e.g. Kim Giang / Định Công rows labelled Thanh Xuân / Phương Liệt).
  The proper fix belongs in the unified-dataset pipeline (add a 2025 ward crosswalk); this recommender only repairs the worst case.

## 5. Evaluation (self-rated — not user feedback)
I rated the top-5 of 5 personas (25 listings) 1–5 from listing text only (no photos, no site visits). Use it to find bugs, not to claim quality.

| Stage | Mean rating | Listings rated ≥ 4 |
|---|---|---|
| Initial | 2.60 | 24% |
| After removing shared ads + nulling fallback geo | 3.16 | 28% |
| After the price-score change | 3.52 | 52% |
| After the geocoding fix | 3.52 (top-5 unchanged) | 52% |

Weakest persona: SV UTC (3.0): several results still show distances to UTC that look doubtful (ward-level coordinates), and near-duplicate YourHome units (same building, 3.6M vs 4.0M) are not merged because prices differ by more than 5%.
A "dormitory" listing carries `pet_allowed = 1`, probably a wrong amenity label. The 25 ratings in `data/recsys_eval_labels.csv` should be confirmed or replaced by a human before anything (e.g. learned weights) is built on them.

## 6. How to reproduce
```bash
pip install -r requirements.txt
python -m src.recsys.regeocode_fallback      # ~35 Nominatim requests (cached afterwards)
python -m src.recsys.dedup_unified           # ~70 s
python -m src.recsys.recommend --budget 4000000 --district "Cầu Giấy" --need air_conditioner --top 10
streamlit run src/recsys/app.py
python -m src.recsys.evaluate
python -m pytest tests -q
```

## 7. Repository notes
- `data/` and `/docs/` are gitignored; `docs/*.md` files already tracked before (PLAN.md etc.) stay tracked. Nothing has been committed.
- Tracked files changed: `requirements.txt`, `src/clean/sample_schema.py` (`cross_platform` option), `tests/test_sample_schema.py`. New: `src/recsys/*`, `tests/test_recommend.py`, `tests/test_regeocode_fallback.py`.
- Open items: human rating of the evaluation sheet; ward crosswalk in the pipeline; recompute value residuals after geo fixes; learned weights only if real feedback exists.

## 8. Rating study (provisional)
See docs/RECSYS_RATING_STUDY.md: model-rated head-to-head study of default scoring vs cheapest-first on 10 personas (mean 3.78 vs 3.12, default wins 10/10); all ratings are Claude-assigned placeholders pending human rating.

## 9. Small improvements (2026-10-05)
**Map layers (app).** `src/recsys/app.py` now draws all 22 universities (green graduation-cap markers) and 20 metro stations (purple dots, with line name) from `src/recsys/ref_points.py`;
a sidebar checkbox toggles them. Checked with `streamlit.testing` (no exception) only; not looked at in a real browser.

**More shared-room patterns.** `SHARED_RE` also catches "Home stay" (with a space), per-person prices written as `1tr3/ng`, and "share". The "/ng" rule requires a digit before it,
so "hộ gia đình/ng đi làm" is not caught. Dorm ads ("KTX", "ký túc xá") are treated as shared only when the price is under 2.5M. `load()` now stores the result in an `is_shared` column.
Effect: 4.2% of listings are flagged shared (was ~4.2% before for the old pattern plus the new variants; the figure barely moved because most variants were already covered).

**Correction about the dorm listing.** Earlier I suggested the `pet_allowed = 1` flag on "Trọ Ký Túc Xá Đại Học Thuỷ Lợi" was probably wrong. I checked: the listing is 40 m², 4.2M, with a normal amenity list
that explicitly includes "Thú cưng" in the source data, so I found no evidence of a wrong label and did **not** change it. The title likely means "boarding house near Thủy Lợi University". It is not flagged as shared because of its price.
The rating 2 I gave it earlier was based on that unverified suspicion; treat it as a possibly harsh rating.

**Near-duplicate buildings — handled at recommendation time, not by merging.** Units with the same house/alley number in one district (e.g. several rooms at "ngõ 189 Hoàng Hoa Thám", 3.6M vs 4.0M, different areas)
can be genuinely different rooms, so merging them in the data would risk deleting real listings. Instead `recommend(..., per_building=1)` (CLI `--per-building N`, 0 = off) shows only the best-scoring room per building.
Listings whose address has no house/alley number are exempt. The pet-friendly persona's top-5 now shows one Hoàng Hoa Thám unit instead of two, and a new Nghi Tàm listing (rated 4) entered the list.

**Tests / checks.** 60 tests pass (new: `test_more_shared_variants_and_dorm_beds`, `test_one_room_per_building`). `evaluate.py` re-run: the default config still returns 10 results for all 20 personas;
24 of the 25 earlier ratings still match the current top-5 and the one new listing was rated 4 (mean of the 25 ratings stays 3.52; still model-assigned).
