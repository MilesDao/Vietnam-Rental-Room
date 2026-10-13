# Hanoi Rental Recommender — Detailed Update Report

Period: 2026-10-04 → 2026-10-05 · Project: Vietnam Rental Room (USTH) · Author: Claude (assistant), reviewed by the project owner.
Every change below is classified as **Added**, **Fixed** or **Improved**. All numbers were produced by code in this repository and can be re-run (section 6).

> **Update 2026-10-06 — read section 9 first.** The data was refreshed: Facebook (earlier cleaned data) + a Hanoi-only re-crawl of six
> sites → 9,283 listings, 7,167 distinct rooms. Sections 0–8 describe the earlier 15,861-listing dataset and were **not** rewritten;
> the numbers in them (15,861 / 13,558 rooms, MAPE 18.4%, the 538 fake-coordinate rows, the persona ratings) belong to that dataset.
> Section 9 lists what changed, the new numbers, and what could not be re-measured.

## 0. Context and result in one page
- **Data used.** `data/` was copied from the remote branch `origin/unified-crawl-data` (nothing merged, no local file overwritten):
  `unified_hanoi_rentals.csv` — 15,861 listings, 58 columns, 7 platforms (Phongtro123 4,820 · Facebook 4,672 · Chotot 3,631 · Mogi 1,725 · Rencity 862 · YourHome 84 · Alonhadat 67).
- **Method.** Knowledge-based / content-based recommender: hard-constraint filtering + multi-criteria weighted scoring. It is **not** a machine-learning model (no user data exists yet).
- **Outcome.** A working CLI and a Streamlit map app; 4 data/ranking bugs found by evaluation and fixed; 60 automated tests passing.
- **Quality evidence (provisional).** Model-assigned ratings: mean 2.60 → 3.52 /5 on 5 personas across the fix stages; default scoring beat a "cheapest first" baseline on 10 of 10 personas (3.78 vs 3.12).
  **No human has rated anything yet**, so quality claims are preliminary.

| Category | Count | Items |
|---|---|---|
| Added | 7 | recommender core · Streamlit map app · cross-platform dedup · area estimation · geocoding repair tool · evaluation harness · tests/README |
| Fixed | 8 | shared-room swamp · shared-variant misses · fake fallback coordinates · Streamlit import error · numpy bug · ratings overwritten · (non-)fix of a dorm label · map crash on titles containing braces |
| Improved | 4 | price score · one room per building · value-score fallback · map layers |

## 1. Added (new capabilities)
| # | What | Where | Notes |
|---|---|---|---|
| A1 | **Recommender core**: filters (max rent, district, min area, required amenities, nearest university + max km, max metro km, house type) then score = 0.30 price fit + 0.25 value (`value_residual_pct`) + 0.25 distance (to the chosen university, else to the centre) + 0.20 amenities | `src/recsys/recommend.py` | CLI: `python -m src.recsys.recommend --budget ... --district ...`. Output contains no contact data. |
| A2 | **Streamlit app redesigned after yourhome.top** (2026-10-05): left sidebar filters (price range, room type, area, amenities, district, near-university, source, shared-ads checkbox); "N kết quả phù hợp"; sort box (best match / price / area / near centre); page size 8/12/24/48/100; photo cards with type badge, price, area, address, "Xem tin" and "Bản đồ" popup; "Trang x/y" pagination; a map view where the user clicks a point and picks a radius (0.5–10 km) to list nearby rooms; map dots for all matches (up to 5,000, drawn in the browser by `FastMarkerCluster`, ~10x faster than one folium object per room) | `src/recsys/app.py` | `streamlit`, `folium`, `streamlit-folium` added to `requirements.txt`. Not copied from the site: two-point search, poster-type filter (replaced by "Nguồn tin"), newest-first sort and lease-expiry date (data not available). Facebook posts never show photos (project privacy rule). The earlier university/metro markers were removed at the owner's request. |
| A3 | **Cross-platform duplicate removal**: 15,861 → 13,673 listings (2,188 folded, ~2,000 of them Facebook, a source never deduplicated before) | `src/recsys/dedup_unified.py`, `sample_schema.mark_duplicates(cross_platform=True)` | Same rules as the existing same-platform dedup: price ±5%, area ±1 m², same title or house/alley-level address, complete linkage, keep the row with most fields. |
| A4 | **Missing-area estimate** (37% of listings lack area): `area_est` + flag `area_imputed` | `recommend.impute_area()` | Median by house type × price quintile. Holdout MAE 7.8 m² vs 10.5 m² for a global median (modest gain). Used for scoring/display only; the `--min-area` filter uses real areas. |
| A5 | **Geocoding repair tool** (see F3) | `src/recsys/regeocode_fallback.py`, `ref_points.py` | Uses the project's cached, rate-limited Nominatim client. |
| A6 | **Evaluation harness**: 20 personas × 5 weight settings, behavioural metrics, label sheets | `src/recsys/evaluate.py` → `docs/RECSYS_EVAL.md`, `data/recsys_eval_labels*.csv` | Plus the rating study `docs/RECSYS_RATING_STUDY.md`. |
| A7 | **Tests and docs**: `tests/test_recommend.py`, `tests/test_regeocode_fallback.py`, extra case in `tests/test_sample_schema.py`; README "Recommender" section with a manual Streamlit checklist | `tests/`, `README.md` | 60 tests pass. |

## 2. Fixed (bugs, each with cause → fix → effect)
| # | Problem (how it was found) | Root cause | Fix | Effect |
|---|---|---|---|---|
| F1 | Shared-room ads filled the top of the results (2.8% of data but **42%** of the top-10) — found by the first persona evaluation | A slot is priced per bed but lists the whole room's area, so `value_residual_pct` had median −57% and 60% were labelled "bargain" | Exclude shared ads by default (`SHARED_RE`, `is_shared` column); `--include-shared` / UI checkbox to bring them back | Shared share of the top-10 → 0% |
| F2 | Per-person ads still slipped through (found while rating results) | Keyword list too narrow | Added "homestay / Home stay", "sleep box", "1 người", "/người", prices written `1tr3/ng` (a digit must precede, so "hộ gia đình/ng đi làm" is not hit), "share"; dorm/KTX ads only when price < 2.5M | 4.2% of listings flagged. **Heuristic**: further variants may remain. |
| F3 | Persona "SV UTC" was shown rooms ~30 km away "0.11 km from UTC" | 538 Phongtro123 rows (3.4%) shared one coordinate (21.028511, 105.804817 — also UTC's campus) although addresses named 35 different post-2025 wards; those ward names evidently had no entry in the pipeline's centroid table | `regeocode_fallback.py` geocodes each affected ward once (35 queries; 31 sent, 4 cached; ≤1 req/s), assigns ward centroid, legacy district by point-in-polygon, recomputes distance/metro/university features; `null_fallback_geo()` kept as a guard | 428 of 538 rows regained valid coordinates (Sóc Sơn 8 → 98 listings, Thạch Thất 5 → 22, Thanh Trì 471 → 548). 110 rows stay without coordinates: wards outside Hanoi (Vũng Tàu, Bến Cát…) or not found. |
| F4 | `streamlit run` failed: `ModuleNotFoundError: No module named 'src'` (reported by the owner) | Streamlit puts `src/recsys` — not the repo root — on `sys.path`; my earlier check ran under pytest, which hid this | `app.py` inserts the repo root into `sys.path`; `recommend.py` locates the data file relative to its own path | Verified from a fresh interpreter in a different working directory. |
| F5 | `price_score()` crashed on numpy arrays — caught by its own new unit test | `.clip(lower=…)` exists only on pandas objects | Replaced by `np.maximum` | Test passes. |
| F6 | Re-running `evaluate.py` blanked the rating column | Label file was rewritten from scratch | Existing ratings are merged back by (persona, listing) | Ratings survive re-runs. |
| F7 | *Correction, nothing changed.* I had suspected the `pet_allowed=1` flag on "Trọ Ký Túc Xá Đại Học Thuỷ Lợi" (4.2M, 40 m²) was wrong | The source amenity list explicitly includes "Thú cưng"; the title probably means "near" the university | No change made (no evidence of an error). The rating of 2 I gave it earlier may be too harsh. | — |
| F8 | App crashed (`TemplateSyntaxError`) when a top result had braces in its title, e.g. `{ẢNH THẬT 100% }` or `}}{{` (found by the Streamlit test run) | folium renders popups through a Jinja template, so `{{`/`{%` in text is treated as template code | All text put into popups is HTML-escaped and braces are written as entities (`esc()`) | 2 affected titles render fine. |

## 3. Improved (existing behaviour made better)
| # | Before → after | Evidence |
|---|---|---|
| I1 | **Price score.** Before: `1 − price/budget`, so the cheapest ad always won (top results at 1.0–1.6M while only 5% of listings are ≤ 1.5M; median 3.9M). After: score peaks at the typical price of the same house type × district, falls off for suspiciously cheap rooms, and declines only mildly toward the budget | Mean price/budget of the top-10: 0.47 → 0.76; model-rated mean 3.16 → 3.52 and share of listings rated ≥ 4 28% → 52% (5 personas) |
| I2 | **One room per building.** Before: near-identical units of one building (e.g. "ngõ 189 Hoàng Hoa Thám", 3.6M and 4.0M) filled several top slots. After: best room per house/alley number per district (`--per-building N`, default 1, 0 = off). Done at recommendation time rather than by merging because such units can be genuinely different rooms (different areas) | Pet-friendly persona top-5 shows one such unit instead of two |
| I3 | **Value score when `value_residual_pct` is missing** (37% of rows): neutral 0.5 → rank of price per estimated m² (`area_est`) | Not measured separately (the evaluation table's estimated-area share fell 28% → 12% in the same run as I1, so it cannot be attributed to this change alone) |
| I4 | **Map**: all matching listings as soft pastel price-label pins (green < 3M, blue 3–5M, rose > 5M) with grey numbered cluster discs; clicking a number glides and zooms into the area its rooms cover (`flyToBounds`, 0.9 s; rooms sharing one spot spiderfy); clicking an empty point glides there (from the previous point, so movement is continuous) with a slowly pulsing dashed ring and lists rooms within 0.5–10 km; fractional zoom steps and re-enabled zoom/fade animations for smooth movement. Replaces the numbered pins and the university/metro markers | JavaScript syntax (Node) and script order checked (map → cluster → click handler → ring → fly-in; an earlier version emitted the fly-in before the map and would have failed); app run with Streamlit's test runner incl. two successive clicks. **Not yet seen in a browser by anyone**: smoothness, colours and timings are unconfirmed by eye |

## 4. Evaluation evidence (model-assigned ratings — read the caveat)
Ratings (1–5) were assigned by Claude from listing text only (title, description, price, area, district, distance fields); no photos or site visits.
For the head-to-head study Claude knew which list came from which configuration and also wrote the system, so the gap is an upper bound.

| Stage (5 personas, 25 ratings) | Mean | Rated ≥ 4 |
|---|---|---|
| Initial | 2.60 | 24% |
| After F1 + F3 safety net | 3.16 | 28% |
| After I1 (price score) | 3.52 | 52% |
| After F3 repair, F2, I2 | 3.52 | 52% |

| Head-to-head (10 other personas, 100 ratings) | Mean | Rated ≥ 4 |
|---|---|---|
| Baseline "cheapest first" | 3.12 | 28% |
| Default scoring | **3.78** | **72%** |

Default beat the baseline on 10/10 personas, mean difference +0.66 (bootstrap 95% interval over personas +0.42…+0.94, n = 10, rough). Over all 15 personas the default scores 3.69 and 65% ≥ 4.
Weights 0.30/0.25/0.25/0.20 were set by hand and perform about the same as equal weights (0.25 each); they were **not** changed.

## 5. Known limitations and open items (after the v2 upgrade, section 8)
1. **No real feedback yet.** The app now collects 👍/👎 and a learning-to-rank step is ready, but until ≥ 200 votes from ≥ 5 sessions exist the weights stay hand-set and the only quality ratings are AI-assigned.
2. **Coordinates are ward-level** for many listings (e.g. hundreds of Phongtro123 rows share one ward centre); distances are approximate.
3. **Ward/district labels** still disagree with the address text in many rows; the real fix is a 2025 ward crosswalk in the upstream pipeline.
4. **Shared-room detection** is keyword-based; **post dates** exist for only ~30% of ads.
5. The app has not yet been reviewed visually in a browser by a person (checklist in `README.md`).
Resolved by v2: stale value scores, the 12 M-budget persona getting 3 M rooms, raw phone numbers in the data, the nearest-campus-only university filter, out-of-Hanoi rows, no stale-ad filter.

## 6. Reproduce
```bash
pip install -r requirements.txt                 # now includes scikit-learn
python -m src.recsys.prepare                    # geo repair, drop, hash phones, dates, dedup, ML models (~1-2 min)
python -m src.recsys.price_model --report       # CV errors of the ML models vs baselines
python -m src.recsys.recommend --budget 4000000 --district "Cầu Giấy" --need air_conditioner --top 10
streamlit run src/recsys/app.py
python -m src.recsys.ltr                        # learning to rank from collected feedback
python -m src.recsys.evaluate
python -m pytest tests -q                       # 67 passed
```

## 7. Files
- **Recommender package `src/recsys/`:** `prepare.py` (data preparation), `regeocode_fallback.py` + `ref_points.py` (geo repair), `price_model.py` (ML area + fair price), `recommend.py` (engine + CLI), `similar.py` (TF-IDF similar rooms / text search), `feedback.py` (SQLite feedback store), `ltr.py` (learning to rank), `app.py` (Streamlit), `evaluate.py`, `make_slide_figures.py`. `dedup_unified.py` was removed (folded into `prepare.py`).
- **Tests:** `tests/test_recommend.py`, `tests/test_regeocode_fallback.py`, `tests/test_ml.py`, a cross-platform case in `tests/test_sample_schema.py`.
- **Changed (tracked):** `requirements.txt`, `README.md`, `src/clean/sample_schema.py` (`cross_platform` option), `tests/test_sample_schema.py`, `.gitignore` (`/docs/`).
- **Generated (gitignored):** `data/unified_hanoi_rentals_geofixed.csv`, `data/unified_hanoi_rentals_dedup.csv`, `data/models/price_model.joblib`, `data/recsys_feedback.sqlite`, `data/models/ltr_weights.json` (only once learned weights win), evaluation label sheets.
- Credit: coordinates derived from Nominatim — © OpenStreetMap contributors (ODbL). Nothing has been committed or pushed.

## 8. Upgrade v2 (2026-10-05): correct data, ML, real evaluation, new app features
Method is now an **ML recommender** (see the 2026-10-05 decision at the end: a learned ranker is deployed): content-based hard filtering + a weighted score, whose *value* part comes from an
ML fair-price model, with free-text search by TF-IDF and score weights learnable from real feedback.

**Data preparation (one command, `prepare.py`)**
| Change | Result |
|---|---|
| Geo repair now part of the pipeline | same 428/538 repaired rows (answers from the Nominatim cache) |
| Drop un-locatable fallback rows and rows outside Hanoi | −110 (no findable ward; mostly outside Hanoi) and −6 (city = Hồ Chí Minh) |
| Phone numbers hashed with the project salt (`src/crawl/pii.py`); poster names dropped | 0 raw numbers left (checked by a test); Facebook values were already SHA-256 hashes |
| Post dates parsed | `days_old` for ~30% of ads (relative to the newest post in the snapshot) |
| Cross-platform dedup | 15,745 → 13,558 distinct rooms (2,187 duplicates) |

**ML models (`price_model.py`, gradient-boosted trees, 5-fold out-of-fold predictions, trained on distinct non-shared rooms)**
| Model | ML error | Baseline error |
|---|---|---|
| Missing area (8,928 training rooms) | MAE 6.38 m² | 7.24 m² (house type × price-quintile median) — so ML is used |
| Fair price (12,975 training rooms) | MAPE 18.4%, MAE 0.92 M VND | 38.5%, 1.78 M VND (median of house type × district) |
| Fair price vs the branch's Ridge model, same 8,893 rows | MAPE 21.8% (out-of-fold) | 31.2% (Ridge, in-sample) |
The value score now exists for every row and uses repaired locations; `market_value_tier` is recomputed (±15%). Cards
show it in words ("Rẻ hơn ~12% so với phòng tương tự") and the comparison table shows the fair price.

**Ranking changes (`recommend.py`)**: distance to the *chosen* campus (all matching campuses, default ≤ 3 km) instead of
"nearest campus = X"; price anchor ≥ 70% of the budget (a 12 M budget no longer favours 3 M rooms); optional
"posted within N days" filter (undated ads kept); weights read from learned-weights file when published.

**Real evaluation (`feedback.py`, `ltr.py`, `evaluate.py`)**: every shown card is logged as an impression with its score
parts; 👍/👎 votes are stored (SQLite, random session id, no personal data). `ltr.py` fits a logistic regression on the
score parts, evaluates by session-grouped CV with NDCG@10 and precision@5 against the hand weights and cheapest-first,
and publishes learned weights only with ≥ 200 votes from ≥ 5 sessions and a held-out win. `docs/RECSYS_EVAL.md` now has a
real-feedback section (currently: none collected) separate from the synthetic persona table.

**App features (`app.py`, `similar.py`)**: free-text search blended with the score; ≈ similar rooms (TF-IDF on text + price,
area, location); ♡ save and a side-by-side comparison of up to 4 rooms; two-point radius search (e.g. school + work);
filters stored in the URL for sharing; no phone numbers anywhere.

**Checks**: 67 tests pass (new `tests/test_ml.py`: chosen-campus distance, budget anchor, phone hashing, no raw phone in the
prepared file, out-of-fold predictions, feedback round-trip + learning to rank on synthetic votes, similar rooms / text search).
App exercised with Streamlit `AppTest` (home, vote, save, similar, text search, university, date filter, saved view,
map, two points) against a temporary feedback database. Not yet viewed in a real browser.

**AI-labelled feedback run (2026-10-05, at the owner's request).** To exercise the learning-to-rank pipeline, the assistant
read the top 25 results of 10 new searches (students near NEU, VNU, PTIT, HaUI; a worker in Cầu Giấy; studios in Đống Đa; a
couple in Thanh Xuân; a high budget with elevator; Hoàng Mai with washing machine; Ba Đình/Tây Hồ) and gave 👍/👎 to all 250
listings from their text. Stored separately in `data/recsys_feedback_ai.sqlite` (sessions `ai-q1…q10`), never mixed with the
real feedback database.

| Ranking | NDCG@10 | Precision@5 |
|---|---|---|
| Hand-set weights (current) | **0.851** | **0.90** |
| Learned weights, session-grouped CV | 0.829 | 0.86 |
| Cheapest first | 0.602 | 0.48 |

72% of listings got 👍 (82% in the top 10, 65% at ranks 11–25). Learned weights (price 0.54, distance 0.40, amenities 0.07,
value 0) did **not** beat the hand-set ones on held-out searches, so nothing was published and the app keeps the hand-set
weights. Most 👎 were caused by things the four score parts cannot see: district labels that disagree with the address
(e.g. Linh Đàm or Định Công listed under Thanh Xuân, Văn La under Đống Đa), several ads for the same building,
sublet/"pass"/"nhượng" posts, female-only or shared rooms, and vague ads without an address. Next useful features are
therefore data-quality signals (address–district mismatch, sublet keywords), not different weights. These are one
assistant's judgements, not users' — they show the pipeline works, not that the ranking is good for people.

**Learning to rank from the assistant's 250 votes (2026-10-05, at the owner's request).** `python -m src.recsys.ltr --db
data/recsys_feedback_ai.sqlite` trains on the AI-labelled database directly (it is not merged into the real-feedback database;
an attempt to merge was blocked because it would have made AI votes indistinguishable from users' votes). Three data-quality
signals were added as learnable score parts (not a sublet/"pass"/"nhượng" ad, has a house/alley address, district label agrees
with the address); with hand-set weights they count 0.

| Learner (session-grouped CV on 250 votes) | NDCG@10 | Precision@5 | Deployed? |
|---|---|---|---|
| Hand-set weights (current) | 0.851 | 0.90 | yes |
| Learned: 4 parts only | 0.829 | 0.86 | no |
| Learned: 4 parts + 3 quality signals (final) | 0.835 | 0.88 | no |
| Learned with a "female-only ad" signal as well | 0.845–0.857 | 0.88 | rejected (see below) |

The only variant that beat the hand-set weights did so by learning a large penalty for "female-only" ads. That reflects the
assistant's generic personas, not users, and would push suitable rooms down for women, so that signal was removed from the
learner (it is still computed as `q_any_gender`). Conclusion: on these 250 AI-assigned votes, learning does not improve the
ranking; the app keeps the hand-set weights, and the pipeline will publish learned weights automatically once real feedback
lets them win on held-out searches.

**Is the hand-set vs learned difference real? (paired bootstrap over the 10 searches, 10,000 resamples)**
| Comparison (NDCG@10) | Mean difference | 95% interval | Reading |
|---|---|---|---|
| Hand-set weights − cheapest first | +0.249 | [+0.128, +0.351] | real (excludes 0) |
| Learned weights − cheapest first | +0.233 | [+0.065, +0.387] | real |
| Hand-set − learned weights | +0.016 | [−0.058, +0.096] | cannot tell (includes 0); each wins on 5 of 10 searches |
So the hand-set weights are *not* shown to be better than the learned ones; the learned weights were simply not shown to be
better, which is why they were not deployed. Biases that favour the hand-set ranking: the votes were given on lists ordered by
it (position bias) and the 25 candidates per search came from it (selection bias). Code: `ltr.per_search`, `ltr.bootstrap_diff`;
figures `m7_evaluation.png`, `x4_per_search.png` (the slide deck itself no longer shows the hand-set comparison; see docs/SLIDES_SCRIPT.md, Q&A).

## Decision (2026-10-05, owner): deploy the ML ranker although the evidence is weak
The owner chose to make the ML (learning-to-rank) ranker the recommender even though it is not shown to beat the hand-set
weights. Implementation: `python -m src.recsys.ltr --db data/recsys_feedback_ai.sqlite --force` publishes the learned weights
(`data/models/ltr_weights.json`, marked `forced: true`, source `ai-labelled`); `recommend()` uses them by default
(`ranker="ml"`), the app has a "Cách xếp hạng" switch (Học máy / Trọng số tay) and the CLI has `--ranker hand`.

| | Weights |
|---|---|
| Hand-set | price 0.30, value 0.25, closeness 0.25, amenities 0.20 (quality signals 0) |
| **Learned (deployed)** | price 0.247, value **0.000**, closeness 0.232, amenities 0.022, not-sublet **0.446**, has-address 0.011, district-matches 0.042 |

| Held-out (session-grouped CV, 250 AI-assigned votes, 10 searches) | NDCG@10 | Precision@5 |
|---|---|---|
| Cheapest first | 0.602 | 0.48 |
| Hand-set weights | 0.851 | 0.90 |
| ML ranker (learned) | 0.835 | 0.88 |
ML ranker − hand-set: −0.016, 95% bootstrap interval about [−0.10, +0.06] (cannot tell; 5 wins each). ML ranker − cheapest first:
+0.233 [+0.065, +0.387] (real).

How to read it, honestly:
- The learned ranker gives the fair-price ("value") signal weight 0 and about half of the weight to the data-quality signals;
  those equal 1 for almost every room, so in practice it ranks mostly by price fit and closeness and pushes down sublet ads.
  The fair-price model is still used for the "cheaper/dearer than similar rooms" hint and the compare table.
- It was trained on only 250 votes from one AI assistant, on candidates produced by the hand-set ranking (position and
  selection bias favour the hand-set weights). The comparison is therefore not conclusive in either direction.
- The "female-only ad" signal is computed (`q_any_gender`) but excluded from learning, because a penalty learned from generic
  personas would push suitable rooms down for women.
- Next: collect real votes in the app (👍/👎), retrain with `python -m src.recsys.ltr` (it publishes only with ≥ 200 votes from
  ≥ 5 sessions and a held-out win), and delete `data/models/ltr_weights.json` to go back to hand-set weights.

**Random-order baseline (added for the slides).** `ltr.random_baseline` computes the expected NDCG@10 / precision@5 of a random
order of each search's 25 rooms: 0.722 / 0.716 (most rooms are liked, so random is already high). ML ranker (held-out) 0.835 / 0.88;
cheapest-first 0.602 / 0.48, i.e. *worse than random*. Bootstrap gains in NDCG@10: ML ranker − random +0.113 [+0.036, +0.196];
ML ranker − cheapest first +0.233 [+0.065, +0.387].

## 9. Data refresh (2026-10-06): fresh Hanoi data + Facebook, working links and images
**Request.** Re-crawl the newest Hanoi rental data from every source except Facebook, with a link that opens the right ad and
images that load; then use that data plus the earlier cleaned Facebook data for the recommender. Plan:
`docs/superpowers/plans/2026-10-06-recrawl-fresh-data.md`.

### 9.1 Data now used (`data/unified_hanoi_rentals_dedup.csv`)
| Source | Rows | Origin | Notes |
|---|---|---|---|
| Facebook | 4,672 | earlier cleaned file, unchanged | no post dates; 2,005 of its rows are duplicates of other posts/sites |
| Nhatot (ex-Chotot) | 1,748 | API crawl, 2026-10-06 | newest ad that day, oldest 51 days; links built from `list_id` |
| Mogi | 1,719 | re-walk of the Hanoi category pages | only **2 new ads** (the site had nothing newer than the Sept crawl); no post dates |
| YourHome | 520 (was 84) | site's embedded JSON | 0–44 days old |
| Rencity | 470 | public API, Hanoi only | 0–21 days old; **no area at all** (the API has none) |
| Alonhadat | 77 | partial | **CAPTCHA** after 23 new ads; crawler stopped as designed, not retried or bypassed; no post dates |
| Phongtro123 | 77 | 120 list pages | most ads found were expired or not rooms; 1–89 days old |
| **Total** | **9,283** | | **7,167 distinct rooms** after cross-platform dedup (2,116 duplicates) |

Hanoi only everywhere. Only ~30% of rows have a post date (38% of distinct rooms); the rest cannot be age-filtered. Dated ads
older than 180 days are dropped (none remained). Prices outside 500,000–50,000,000 VND/month and shops/offices are dropped.

### 9.2 What was wrong with links and images, and the fix
| Source | Problem found | Fix |
|---|---|---|
| Mogi | exporter *fabricated* `https://mogi.vn/dummy-id<N>` (404) from the raw file name | exporter reads the real URL from the crawl database (`src/export/export_mogi_to_sample.py`) |
| YourHome | every row linked to the home page | `https://yourhome.top/room/<id>` (the site's own card links) |
| Rencity | `search?post_id=N` = the generic search page | `https://rencity.vn/post/<slug>-<id>` (server-rendered; a made-up id gives an empty title, so it is checkable) |
| Nhatot | old `nha.chotot.com` links redirect; detail pages answer scripts with 403 | `https://www.nhatot.com/thue-phong-tro/<list_id>`, built from the API; never fetched as HTML |
| Phongtro123 | parser took every `<img>` on the page, incl. thumbnails of *other* ads | only the ad's own gallery (`div.post__photos .carousel-item`), tested on a saved page |
| App | regex left a stray `"` on every URL of a JSON image list | `app.py` uses the shared `parse_images` |

Shared contract in `src/clean/link_check.py` (per-platform permalink shape, one image-list format); `prepare.gate_links` blanks any
link that is not a permalink or is shared by several rows (Facebook excluded: several rooms may share one post).

### 9.3 Live check (`python -m src.crawl.verify_sample data/unified_hanoi_rentals_dedup.csv --n 25 --skip Alonhadat.vn`)
| Source | Links open the right ad | First image loads (no Referer) |
|---|---|---|
| Mogi | 100% | 96% |
| Phongtro123 | 100% | 100% |
| Rencity | 96% | 100% |
| Nhatot | not testable by script (403); built from the id | 100% |
| YourHome | not testable (client-rendered page returns 200 for any id); id checked against the crawl | 100% |
| Alonhadat | **not tested** (our IP was CAPTCHA-blocked) | not tested |

Baseline before the fix: Mogi links 0%, Rencity links 0% and images 50%. Nhatot and YourHome links should be clicked by hand.

### 9.4 ML results on the new data
| Model | Training rooms | ML error | Baseline |
|---|---|---|---|
| Fair price (gradient boosting, out-of-fold) | 6,867 | MAPE **15.0%**, MAE 0.67 M VND | 31.9% / 1.26 M (median of type × district) |
| Fair price vs the old Ridge, same 679 rows | 679 | 20.6% | 30.4% (Ridge, in-sample) |
| Missing area (gradient boosting) | 3,540 | MAE 15.17 m² | 15.41 m² (type × price-quintile median) — **only a small gain** |

48% of the distinct rooms have no area (Facebook 76%, Nhatot 59%, Rencity 100%), so `area_est` matters; estimated areas are flagged.
The earlier figures (MAPE 18.4% vs 38.5%; area MAE 6.38 vs 7.24 m²) were on a different dataset and are not comparable.

### 9.5 What could NOT be re-measured (read before quoting results)
- **Ranker evaluation was not recomputed.** `ltr.labelled()` joins the quality signals to each vote by `listing_id` and fills
  rooms it cannot find with 1.0. Of the 250 AI-assigned votes, only 100 rooms exist in the new data (Phongtro123 2 of 100 and
  Nhatot 3 of 45 survive, because those old ads were replaced), so a recomputation would be distorted. The deployed weights
  (price 0.247, value 0, closeness 0.232, amenities 0.022, not-sublet 0.446, has-address 0.011, district-ok 0.042; `forced: true`)
  are unchanged, and the held-out numbers in section 8 (NDCG@10 0.835, P@5 0.88; random 0.72/0.72; cheapest-first 0.60/0.48) stand as
  *measured on the earlier dataset*. Votes are still AI-assigned, 10 searches, no real users.
- The persona tables (`docs/RECSYS_EVAL.md`) were regenerated on the new data and still run 20/20 personas, but they are synthetic.
- Nothing was viewed in a real browser; the Streamlit `AppTest` smoke run raised no exception.

### 9.6 Bugs found and fixed while merging (each has a test)
- Mogi ids came out as `mogi_mogi_…`; Rencity/YourHome ids changed prefix (`RC_`/`YH_` restored so votes still join).
- Rows with price/area 0 or implausible prices (2 VND, 300 M) made the price model's `log` infinite (MAPE 20,836% before the fix).
- 9 Phongtro123 rows sat on the old fallback coordinate (21.028511, 105.804817) and were dropped; two recommender tests rely on this.
- `hash_phone` left 9-digit YourHome numbers (leading 0 lost) as **raw** values in the prepared file; it now normalises and never passes
  through an unrecognised value (`test_prepared_data_holds_no_raw_phone` caught it).
- The live checker flagged "404" inside ids like `714041` as a missing page; it now matches whole words, and treats `.webp` served as
  `octet-stream` as an image by its first bytes.
- Alonhadat rows had no coordinates: the ward-level median of old rows in the same district + ward is used (ward-level accuracy).

### 9.7 Shortcuts and risks
- `estimated_total_living_cost` for re-crawled rows is price + a flat median add-on (the original formula is not in this repository).
- Raw phone numbers still sit in `data/interim/recrawl_2026-10/*.csv` (Mogi, YourHome, Phongtro123 exports); the prepared file has hashes only.
- Backups made: `data/*_seen_urls.db.bak-2026-10-06` (only the Hanoi crawl progress was reset), `data/unified_hanoi_rentals_dedup.csv.bak-2026-10-06`.
- Nothing is committed (the working tree already had uncommitted changes and the branch is `main`).

### 9.8 Reproduce
```bash
python -m src.pipelines.merge_fresh               # data/interim/recrawl_2026-10/* -> data/unified_hanoi_rentals_fresh.csv
python -m src.recsys.prepare                      # reads the fresh file when it exists -> unified_hanoi_rentals_dedup.csv
python -m src.crawl.verify_sample data/unified_hanoi_rentals_dedup.csv --n 25 --skip Alonhadat.vn
python -m src.recsys.make_slide_figures           # keeps the ranker-evaluation figures when the voted rooms are gone
python -m pytest tests -q                         # 83 passed
```
New files: `src/clean/link_check.py`, `src/crawl/verify_sample.py`, `src/pipelines/merge_fresh.py`, `crawlers/chotot/recrawl.py`,
`tests/test_link_check.py`, `tests/test_verify_sample.py`. Changed: the Mogi/Alonhadat exporters, the Rencity/YourHome scrapers,
the phongtro123 parser + config (delays 1–2 s, 3 workers), `prepare.py`, `app.py`, `make_slide_figures.py`.

## 10. Re-measurement after the review fixes (2026-10-07)
Source of every number below: `docs/report_numbers.json` (`python -m src.recsys.report_numbers`). The review is
`docs/COUNTER_REPORT.md` and the plan is `docs/PLAN.md` (Phases 1–2). **These replace the section 9 model numbers.**
Intervals are 95%: models use a cluster bootstrap over the fold groups (poster or ~50 m cell, 1,000 draws), the ranker a
paired bootstrap over the 10 searches, and the links a Wilson interval.

### 10.1 What changed in the method
- The fair-price model no longer receives `area_est`. That estimate is computed from the room's own price, which leaked
  that price into the fair price for the 48% of rooms with no stated area. The model now gets the stated area, or
  "missing".
- Folds are grouped by poster (phone hash), else by ~50 m cell, for both models and both baselines (`GroupKFold(5)`).
- Room types are unified into Phòng trọ, Studio, Căn hộ, Chung cư mini, Nhà nguyên căn and Ở ghép. Whole houses stay in
  the data but are excluded from room searches unless selected.
- Mogi and Phongtro123 phone hashes were all missing (a CSV read as numbers), and are now 100%. Phone numbers in ad text
  are redacted (3,552 descriptions had one). Repeated Rencity ids were removed.

### 10.2 Data (9,281 rows, 7,167 distinct rooms)
Facebook is 50.3% of rows and undated. Rooms by type: Phòng trọ 6,079 · Studio 573 · Nhà nguyên căn 274 · Chung cư mini 142 ·
Căn hộ 98 · Ở ghép 1. No stated area: 48.3% of rooms (Rencity 100%, Facebook 74%, Nhatot 59%; Mogi, Alonhadat, YourHome ≈ 0%).
Price median 4.0 M, 99th percentile 15 M VND/month.
**Freshness:** 38% of distinct rooms are dated (Nhatot, Phongtro123, Rencity, YourHome 100%; Facebook, Mogi, Alonhadat 0%).
Dated rooms are 6/11/21 days old at the quartiles, 89 at most, measured on the snapshot of 2026-10-06. The 180-day filter
removed nothing and cannot act on undated rows.

### 10.3 Duplicates
2,114 duplicates: **2,108 on the same platform** (Facebook 2,005, YourHome 51, Nhatot 25, Mogi 18, Rencity 8, Alonhadat 1)
and **6 across platforms** (all Nhatot → Phongtro123, identical title and address). The new cross-site phone rule
(same poster, price ±5%, ≤150 m) found **0** more pairs. Only 7 posters appear on 2+ sites (85 rows), and none of their
rooms match on price and place. Nhatot and Rencity carry no phone, and Facebook's SHA-256 hashes cannot be compared.
**Precision of the merges** (50 pairs: all 6 cross-platform plus 44 random same-platform; `docs/labelling/duplicate_pairs.csv`;
labelled by the AI assistant from the sheet text, 10 pairs verified by opening the pages, **not by a person**):
42 same room, 6 different rooms, 2 unsure. Of the 48 decided, **87.5% [75.3, 94.1]** are the same room. All 6 cross-platform
pairs are correct (6/6). Same-platform: 36/42 = 85.7% [72.2, 93.3]. All 6 errors are one building listing several units at
nearby prices (4.0/4.6/4.7 M; P302/P606/P306; floor 4 vs floor 5) that the 5% price tolerance merges; room or floor numbers in
the text would separate them.

### 10.4 Models (out-of-fold, grouped)
| | n | ML | Baseline | ML − baseline |
|---|---|---|---|---|
| Fair price MAPE | 6,867 | **25.5%** [24.3, 26.8] | 33.8% [32.0, 35.6] (median type × district) | **−8.3** [−9.5, −7.1] |
| Fair price MAE | 6,867 | 1.09 M VND | 1.34 M VND | |
| … area stated | 3,540 | 22.4% | 35.0% | |
| … area missing | 3,327 | 28.8% | 32.5% | |
| … earlier Ridge, same rows (Ridge in-sample) | 679 | 23.5% | 30.4% | |
| Missing area MAE | 3,540 | 15.52 m² | 15.60 m² (type × price quintile) | −0.08 [−0.39, +0.20] |

By source (ML vs baseline MAPE): Mogi 20.1/29.4 · YourHome 22.3/32.8 · Alonhadat 21.7/43.0 (n=76) · Nhatot 24.7/33.7 ·
Rencity 24.7/24.8 (no gain; no area at all) · Facebook 30.0/36.8 · Phongtro123 30.4/75.5 (n=73).
Effect of the fixes: the leak alone accounts for 15.0% → 23.7% (random folds), and grouping adds 1.8 points.
**The area model is dropped:** its gain's interval spans zero, so `area_est` now uses the type × price-quintile median
(display only; it is not a price-model input). The area MAE interval for each method alone is very wide (≈ 6.5–37 m²),
so a few clusters carry very large errors. This is a target for the error analysis.

### 10.5 Value tiers
Of 6,867 rooms: fair (±15%) **44.5%**, premium 31.1%, bargain 24.4% (before the fix: 65.4% fair). The model's average error
(25.5%) is **wider than the ±15% band**, so a single room's "about 12% cheaper" lies within the noise.

### 10.6 Ranker (250 AI-assigned votes, 10 searches, on the data the votes were cast on)
Quality signals are joined from `data/unified_hanoi_rentals_dedup.csv.bak-2026-10-06`, where all voted rooms exist (only
40% exist in the current data). This reproduces the section 8 numbers exactly.
| Ordering | NDCG@10 | P@5 | Scored on |
|---|---|---|---|
| Cheapest first | 0.602 | 0.48 | all searches |
| Random (expected) | 0.722 | 0.716 | all searches |
| **Nearest first (new)** | **0.823** | 0.88 | all searches |
| **Price fit + closeness, equal weights (new)** | **0.824** | 0.84 | all searches |
| Learned weights | 0.835 | 0.88 | held-out searches |
| Hand-set weights | 0.851 | 0.90 | all searches |

Paired bootstrap of the learned minus each other ordering (NDCG@10): random +0.113 [+0.036, +0.196] · cheapest +0.233
[+0.065, +0.387] · **nearest +0.012 [−0.051, +0.070]** · **price+closeness +0.011 [−0.027, +0.057]** · hand −0.016
[−0.096, +0.058]. Hand-set minus nearest: +0.028 [−0.054, +0.116].
**Reading:** the learned ranker beats only the two weak orderings. It is indistinguishable from simply sorting by
distance, and from the hand-set formula.
Signed standardised coefficients [95% interval]: not-sublet **+0.87** [0.72, 0.98] · closeness **+0.39** [0.12, 1.00] ·
price fit **+0.35** [0.14, 0.75] · value −0.15 [−0.47, +0.31] · amenities +0.09 [−0.20, +0.37] · has-address +0.08
[−0.23, +0.41] · district-ok +0.04 [−0.27, +0.27]. The deployed weight of 0 for "value" is a negative coefficient
clipped to zero. Its interval spans zero, so value neither helps nor hurts measurably in these labels.

### 10.7 Link and image check (Wilson 95% intervals)
| Source | n | Link opens the ad | First image loads |
|---|---|---|---|
| Mogi | 25 | 100% [86.7, 100] | 96% [80.5, 99.3] |
| Phongtro123 | 25 | 100% [86.7, 100] | 100% [86.7, 100] |
| Rencity | 25 | 96% [80.5, 99.3] | 100% [86.7, 100] |
| Nhatot | 25 | not testable by script | 100% [86.7, 100] |
| YourHome | 25 | not testable by script | 100% [86.7, 100] |
| Alonhadat | 0 | not tested (CAPTCHA) | not tested |
| Facebook | 25 | **92% [75.0, 97.8]** (23 of 25; checked by the AI assistant in the user's logged-in browser, 2026-10-07) | not shown in the app |

Before the fix (n = 8 each): Mogi links 0% [0, 32.4], Rencity links 0% [0, 32.4], Rencity images 50% [21.5, 78.5].
The live check was not re-run: Phase 1 changed no links (it only dropped 2 repeated Rencity rows).

### 10.8 Facebook links and manual checks (done 2026-10-07 by the AI assistant, not a person)
All 25 links in `docs/labelling/facebook_links.csv` were opened in the user's logged-in Brave. 23 open a post that matches the
listing's address and price (when a post lists several rooms or a price range, the listing is one of them). 2 show "Bạn hiện
không xem được nội dung này" (deleted, or a restricted audience). Posts are mostly of 9–11 September 2026 (about four weeks
before the snapshot); one is from 15 July (83 days). Facebook rows carry no date in the data, so this is the first age
evidence for them. Two data defects: a price range keeps only its lower bound (4.5–7.5 M → 4.5 M), and one title lost its
location. No names or phone numbers were copied from the posts. A person should still spot-check a few rows.

### 10.9 District labels unified (2026-10-07, during Phase 4) — numbers updated
All 1,719 Mogi rows were labelled "Quận Cầu Giấy" style while every other source writes "Cầu Giấy", so the district feature,
the type × district baseline and **the app's district filter** (which silently dropped every Mogi room) were split. `prepare.unify_districts`
now maps every label to one short name (`sample_schema.short_district`) and looks unknown or composite labels up from the coordinates;
473 Facebook "Chưa rõ" rows have no coordinates and stay without a district. Effect (`docs/report_numbers.json`):
distinct rooms 7,166 (was 7,167), duplicates 2,115, cross-platform **7** (one Mogi → Phongtro123 pair now matches);
price MAPE **25.4% [24.2, 26.8]** vs baseline **34.3% [32.4, 36.2]**, gain −8.9 [−10.1, −7.7]; area stated 22.1/36.0, missing
29.0/32.4; MAE 1.09 vs 1.36 M; Ridge rows 23.7 vs 30.4; area MAE 15.47 vs 15.61 m² (gain −0.14 [−0.41, +0.11], model still dropped);
tiers fair 44.6 / premium 31.0 / bargain 24.4%. Error analysis: median APE 17.0%, 10.7% of rooms off by > 50%; by type studio 18.1%
… whole house 37.8%; by price band 3.6–4.5 M 14.2% vs ≤ 3 M 45.2%; in all 100 worst cases the fair price is above the asking rent
(per-person/bed prices, sublets, teaser prices, lower ends of ranges). The manual-check sheets were not redrawn (the new 7th
cross-site pair is unlabelled). The ranker numbers are unaffected (they use the earlier data).
