# Plan: update and enhance the project report

**Target:** `docs/latex/report.tex` → `docs/latex/report.pdf`
**Input:** the review in `docs/COUNTER_REPORT.md` (section numbers in brackets, e.g. [CR 2.1], point to it).
**Date:** 2026-10-07

**Goal:** every number in the report is re-measured on fixed code, and every claim matches its evidence. The report also gains the sections a marker expects that are missing today: related work, ethics and law, error analysis, reproducibility, contributions and AI disclosure.

**Constraints carried over:**
- Formal style, with no code shown in the report. Settings and parameters go in tables.
- Hanoi only.
- No re-crawling of challenged sites; a challenge is a hard stop.
- Phone numbers are hashed only; never rotate `.project_salt`.
- Build with XeLaTeX (Tectonic). On Overleaf, set the compiler to XeLaTeX.

> **Note on the file name.** Comments in `src/clean/sample_schema.py` and `src/clean/dedup.py` cite "docs/PLAN.md Phase 3" as the original data roadmap. That file no longer exists here, so this plan does not replace it. If the old roadmap is restored, rename this file to `docs/REPORT_PLAN.md`.

---

## Phase 0: Prerequisites (blocking)

| # | Task | Done when |
|---|---|---|
| 0.1 | Let scikit-learn run. Windows Application Control blocks `sklearn\svm\_liblinear*.pyd`. You need to allow it (or use a venv or conda env that is allowed); I will not bypass the control. | `python -c "import sklearn.linear_model"` succeeds |
| 0.2 | Back up the current outputs: `report.tex`/`.pdf` → `*_v2.bak`, `data/unified_hanoi_rentals_dedup.csv` → `.bak-2026-10-07`, `data/models/` → `models.bak-2026-10-07` | backups exist |
| 0.3 | Baseline test run | `python -m pytest tests -q` shows 83 passed (record any failures caused by 0.1) |

**Status (2026-10-07):**
- 0.1 **BLOCKED.** `import sklearn.linear_model` still fails: "DLL load failed while importing _liblinear: An Application Control policy has blocked this file." Needs the user to allow `site-packages\sklearn\svm\_liblinear*.pyd` (or use an allowed environment).
- 0.2 **Done.** Created `docs/latex/report_v2.tex.bak`, `docs/latex/report_v2.pdf.bak`, `data/unified_hanoi_rentals_dedup.csv.bak-2026-10-07`, `data/models.bak-2026-10-07/`.
- 0.3 **Done, with the block.** 75 collected without `tests/test_ml.py`: 69 passed, 6 failed (all `tests/test_link_check.py` tests that import `prepare`, failing on the same sklearn DLL). `tests/test_ml.py` cannot even be collected. Not the expected 83 passed, so Phase 1 cannot be verified until 0.1 is resolved.
- **`.venv` created** (Python 3.12.10, scikit-learn from a fresh wheel). The policy blocks `.venv\Lib\site-packages\sklearn\svm\_liblinear*.pyd` too, so the block is not tied to one path. Inside the venv the results are identical: 69 passed, 6 failed, `test_ml.py` not collectable. `requirements.txt` was missing `shapely` (used by `regeocode_fallback`), `matplotlib` (figures) and `pytest`; these are now added. `playwright` (only `src/crawl/browser_fetcher.py`) was left out on purpose.
- **Resolved (2026-10-07):** the user allowed the sklearn files. Re-run in `.venv`: `python -m pytest tests -q` → **83 passed** in 110 s. **Phase 0 is complete.** Use `.venv\Scripts\python` for everything from here on.

---

## Phase 1: Fix the methods (code; each fix gets one test)

Each fix changes numbers that the report quotes, so all of Phase 1 must finish before Phase 2 measures anything.

| # | Fix | Where | Test | Fixes |
|---|---|---|---|---|
| 1.1 | **Remove the own-price leak.** Drop `log_price` from the area model, so the area estimate no longer uses the room's own price. Keep the `area_imputed` flag. Report MAPE separately for rooms with a stated area and rooms with an imputed one. | `src/recsys/price_model.py` (`add_area`, `add_fair_price`) | `area_est` for an imputed row does not change when only its `price_vnd` changes | CR 2.1 |
| 1.2 | **Group the cross-validation folds.** Replace `KFold` with `GroupKFold`. The group is `phone_hash` when present, otherwise a cluster of coordinates rounded to about 50 m. Apply this to both models and to the median baseline. | `price_model.py` (`_oof`, `_group_median_oof`) | no group appears in both the training and test folds | CR 3.1 |
| 1.3 | **Unify room types.** Map every spelling to one label set: Phòng trọ, Studio, Chung cư mini, Nhà nguyên căn, Ở ghép, Khác. Decide whether whole houses are in scope (recommended: keep them in the data but exclude them from the room recommender by default, and say so). | `src/pipelines/merge_fresh.py` (`finish`) plus the mapping in `src/clean/sample_schema.py` (reuse it, don't duplicate it) | the prepared data contains only the canonical labels | CR 2.3 |
| 1.4 | **Sharpen duplicate detection across platforms.** Add a cross-platform rule: same `phone_hash` + price within 5% + within 150 m. Then hand-label 50 candidate pairs and report the precision of the rule. | `src/clean/sample_schema.py` (`mark_duplicates`) | a fixture pair from two platforms is merged; a different room from the same poster is not | CR 2.2 |
| 1.5 | **Make `listing_id` unique.** Fix the 2 repeated Rencity ids. | `merge_fresh.py` (Rencity adapter) | `listing_id.is_unique` is true | CR 4 |
| 1.6 | **Signed ranker coefficients.** Keep the clipped weights for ranking, but also save the standardised signed coefficients and bootstrap intervals for the report. | `src/recsys/ltr.py` (save only) | the JSON contains `coef_std` and `ci` | CR 2.5 |
| 1.7 | **Add a stronger ranking baseline:** "nearest first", plus price fit and distance with equal weights. | `src/recsys/evaluate.py` / `ltr.py` evaluation | baseline row present | CR 2.4 |
| 1.8 | **Delete or hash the raw-phone interim files.** Ask before deleting anything. | `data/interim/recrawl_2026-10/*.csv` | `grep` finds no 9–11 digit phone numbers | CR 3.8 |

Rebuild: `python -m src.pipelines.merge_fresh && python -m src.recsys.prepare`, then run all tests (must pass).

**Status (2026-10-07): Phase 1 complete.** `.venv` → **89 passed** (83 before + 6 new tests). Streamlit `AppTest` shows no exception. Data rebuilt: 9,281 rows, 7,167 distinct rooms.

| # | Result |
|---|---|
| 1.1 | The fair-price model now uses the *stated* area (missing when unknown), not `area_est`. Test `test_own_price_does_not_leak_through_missing_area` fails on the old code and passes now. |
| 1.2 | Folds are `GroupKFold(5)` by phone hash, else a ~50 m cell, for both models and both baselines (`cv_groups`). |
| 1.1+1.2 effect | **Price MAPE 15.0% → 25.5%** (baseline 31.9% → 33.8%); MAE 0.67 M → 1.09 M VND. The leak alone accounts for 15.0 → 23.7 (random folds); grouping adds 1.8 points. Area stated: 22.4% vs 35.0%. Area missing: 28.8% vs 32.5%. Earlier Ridge, same 679 rows: ML 23.5% vs 30.4%. Area model: MAE 15.52 vs 15.60 m² (no real gain). |
| 1.3 | `canonical_house_type` (in `sample_schema`, applied in `prepare` so Facebook is covered): Phòng trọ 7,735 · Studio 780 · Nhà nguyên căn 359 · Chung cư mini 296 · **Căn hộ** 110 (new label for 1–3 bedroom units, which the plan's list lacked) · Ở ghép 1. Whole houses stay in the data but are excluded from `recommend()` and the app unless selected (`whole_house=`). Facebook's "Phòng trọ / Khác" counts as Phòng trọ. |
| 1.4 | Cross-site rule added (same phone hash + price ±5% + ≤150 m), with a test. **It found 0 new pairs.** Only 7 posters appear on 2+ sites (85 rows), and none of their rooms match on price and place. ChoTot/Rencity have no phone; Facebook's SHA-256 hashes are incompatible. Cross-platform duplicates: **6 of 2,114**. Hand-labelling 50 pairs is moved to Phase 2 (needs a person). |
| 1.5 | Rencity returned 2 ads twice (overlapping API pages); `finish()` drops repeated ids for every source. `listing_id` is unique (tested on the prepared file). |
| 1.6 | `ltr.signed_coefficients`: standardised, signed, 500-sample bootstrap over searches, saved in the report as `coef_std`. Engine weights are unchanged. The JSON gets it on the next `ltr` run (Phase 2). |
| 1.7 | `nearest_first` and `price_plus_distance` baselines in `ltr.evaluate`/`per_search`, plus a note that the fixed orderings are scored on all searches and the learned one held-out. |
| 1.8 | Raw phones in `data/interim/recrawl_2026-10/*.csv` and `*.json` replaced by the project hash (same salt, so the pipeline output is identical; Mogi hashes checked against the pre-hash set). Numbers in ad text redacted. Nothing deleted. Phone-like strings left are hash or image-name false positives. The crawl logs still show numbers inside the ads' public URLs (the site puts them there); left as is. |

**Found and fixed along the way (not in the original plan):**
- **3,552 descriptions in the prepared data (mostly Facebook) contained raw phone numbers**, shown by the app. `prepare.redact_phones` now replaces them with "[SĐT ẩn]" in titles and descriptions, with a test on the prepared file. Poster first names written in the text ("Zalo Phương", "Chị Loan") are **not** removed; that needs a separate step.
- **Mogi and Phongtro123 phone hashes were all missing:** pandas read the numbers as integers and `hash_phone` dropped non-strings. `hash_phone` now accepts numbers, and the adapters read phone columns as text. Coverage went from 0% to 100% for both.

**Consequence for Phase 2/3:** the headline "15.0%, less than half the baseline" no longer holds. Under the decision rule (25.5 / 33.8 = 0.75, above 0.6), the wording becomes **"a modest improvement over a median rule (25.5% vs 33.8%)"**.

---

## Phase 2: Re-measure (numbers the report will quote)

Record every result in `docs/RECSYS_FINAL_REPORT.md` §10 first, then copy it into LaTeX. That gives one source of truth.

| # | Measurement | Command / method | Replaces in the report |
|---|---|---|---|
| 2.1 | Price MAPE/MAE overall, split by stated vs imputed area, and by source; bootstrap 95% CI | `python -m src.recsys.price_model --report` (+ CI) | Summary, Table 3, Figure 4, §6, §8 |
| 2.2 | Area MAE with CI; drop the model if the CI includes no gain | same | Table 3, §3.3 |
| 2.3 | Share of rooms labelled fair, bargain and premium after the fix | prepared data | §3.2 |
| 2.4 | Duplicates: same-platform vs cross-platform counts, and rule precision on 50 labelled pairs | prepared data + labelling sheet | Summary, §2.3, Figure 2 |
| 2.5 | Ranker: signed coefficients with CI; nearest-first baseline; state that the hand-set weights were scored without training | `python -m src.recsys.ltr` (no `--force`) | Table 4, Table 5, Figures 7 and 9 |
| 2.6 | Link check: add Wilson 95% intervals; spot-check 25 Facebook links by hand and record the result | `python -m src.crawl.verify_sample … --n 25` + manual sheet | Table 6, Summary |
| 2.7 | Freshness: dated share by source, and the age distribution of dated rooms | prepared data | §2.1, §7 |

**Status (2026-10-07): Phase 2 measured, except the two manual checks.** All numbers are in `docs/report_numbers.json`, written by the new `python -m src.recsys.report_numbers`. The write-up is in `docs/RECSYS_FINAL_REPORT.md` §10 (backup `.bak-2026-10-07`). `.venv` → **91 passed**.

| # | Result | Decision rule outcome |
|---|---|---|
| 2.1 | Price MAPE **25.5% [24.3, 26.8]** vs baseline 33.8% [32.0, 35.6]; gain −8.3 [−9.5, −7.1] points; MAE 1.09 M vs 1.34 M. Area stated 22.4/35.0, missing 28.8/32.5. By source in §10.4 (Rencity: no gain). | 25.5/33.8 = 0.75 > 0.6 → **"modest improvement"** |
| 2.2 | Area MAE 15.52 vs 15.60 m², gain interval [−0.39, +0.20] | Spans zero → **area model dropped**; `area_est` = type × price-quintile median (`price_model.add_area` now uses an interval rule) |
| 2.3 | Fair 44.5% · premium 31.1% · bargain 24.4% (was 65.4% fair) | Error 25.5% > ±15% band → Phase 3: show the price hint only when it exceeds the segment's error; say so in the report |
| 2.4 | 2,114 duplicates: 2,108 same-platform, **6 cross-platform**; phone rule +0; 7 posters on 2+ sites | Report says "reposts removed; 6 cross-platform". **Precision 87.5% [75.3, 94.1]** of 48 decided (6/6 cross-platform; 36/42 same-platform); labelled by the AI assistant, 10 pairs verified on the live pages |
| 2.5 | Learned 0.835 (held-out) · hand 0.851 · **nearest-first 0.823** · price+closeness 0.824 · random 0.722 · cheapest 0.602. Learned − nearest +0.012 [−0.051, +0.070]. Signed coefficients: value −0.15 [−0.47, +0.31] (the clipped 0) | Learned beats neither hand-set nor nearest-first → **"learning did not improve on a hand-set formula, or on sorting by distance, on AI labels"** |
| 2.6 | Wilson intervals added (25/25 → [86.7, 100]); not re-run (no links changed) | **Facebook: 23/25 = 92% [75.0, 97.8]**, 2 posts unavailable; checked by the AI assistant in the user's browser (`docs/labelling/facebook_links.csv`) |
| 2.7 | 38% of rooms dated (Facebook, Mogi, Alonhadat 0%); dated ages 6/11/21 days at the quartiles, max 89; age filter removed 0 | Report states that most rooms' age is unknown |

Method note for 2.5: votes are joined to the data they were cast on (`data/unified_hanoi_rentals_dedup.csv.bak-2026-10-06`, 100% of voted rooms present), not the current data (40%). This reproduces the earlier 0.835 / 0.88 exactly. `ltr` was **not** re-run as a command, so `data/models/ltr_weights.json` is unchanged and the app's ranker is untouched.

**Decision rules (decide the wording in advance so the results can't steer it):**
- If price MAPE stays below about 0.6 × baseline, keep "substantially better than a median rule".
- If the leak or grouping moves it close to the baseline, rewrite the claim as "modest improvement" and make it a key finding.
- If the fair band (±15%) is smaller than the error for a segment, the app and the report show the price hint only for |value| above that segment's error.
- If the learned ranker does not beat the hand-set weights or nearest-first, the report states "learning did not improve on a hand-set formula on AI labels". No softer phrasing.
- If real votes are collected (Phase 6), re-run 2.5 and replace the AI-label results.

---

## Phase 3: Correct the existing text (claim by claim)

| Section | Change | Fixes |
|---|---|---|
| Executive summary | "learns from users'" → "is designed to learn from users'; trained so far on AI-assigned votes". Drop "clearly outperforms"; report the comparison with the hand-set weights. Use the new MAPE. "Cross-platform merge" → "reposts removed; N cross-platform". Say that half the data is earlier Facebook data. | CR 2.2, 2.4, 3.5 |
| 1.4 Scope | "irreversible hashes" → "salted pseudonymous hashes". Add terms of service and Facebook provenance (see 4.3). | CR 3.8, 3.9 |
| 2.1 Data | Facebook is 50% of rows and undated. The 180-day filter only applies to dated rows (38% of rooms). | CR 3.5 |
| 2.3 Preparation | Describe the new duplicate rule and its measured precision. | CR 2.2 |
| Figure 2 | Caption and figure: split the duplicates into same-platform and cross-platform. | CR 2.2 |
| 3.2 Fair price | Explain how area enters the model without leaking price, and the grouped folds. Add the price interval or the "show hint only when clear" rule. | CR 2.1, 3.1, 3.2 |
| 3.3 Area | Report the CI; say whether the model is kept. Add that unknown-area rooms pass the minimum-area filter, and how the app shows this. | CR 3.3, 3.4 |
| 3.5 Ranking | Explain that coefficients are clipped and why "value = 0" may be a negative association. State the provenance of the forced publication precisely. | CR 2.5, 4 |
| Table 3 row 3 | Relabel the column "earlier model (in-sample)", or drop the row. | CR 4 |
| Table 5 / §5.2 | Add the nearest-first row. Put the caveats (AI labels, old data, 100 of 250 rooms remain) in the caption, not only in §5.4. | CR 2.4 |
| Table 6 | Add the n and the Wilson interval. Add a Facebook row (manual check). | CR 3.6 |
| Figure 3 | Mark the feedback loop as "designed, not yet run with users". | CR 4 |
| §7 Limitations | Connect ward-level coordinates to the distance filter. Remove "estimated total living cost" from the app, or say it is rent + a constant. | CR 3.7, 4 |

---

**Status (2026-10-07): Phase 3 done in the text and tables; the figure images are still old (Phase 5).** `docs/latex/report.tex` → `report.pdf` is now 18 pages (backup of the previous source: `report_v3_before_phase3.tex.bak`; the earlier version is `report_v2.tex.bak`). Every row of the table above was applied, with these additions:
- Executive summary: 25.5% vs 33.8% "modest improvement"; 9,281 listings; half is undated Facebook; only 6 cross-site duplicates; the ranker beats only random and cheapest-first; a short account of the 15.0% → 25.5% correction; the assistant also labelled the duplicate and Facebook samples.
- §1.4 pseudonymous (not "irreversible") hashes, masked phones in text, Facebook provenance and terms of service. Facebook provenance (from the user, 2026-10-07): the posts were collected by a Claude Code agent; the report now says so. Still to document in Phase 4.3: whether it ran logged in, the date, and which groups.
- §2: two new defect rows (room types, phones in text) plus Rencity repeats; Table 1 (468 and 9,281); duplicate split 2,108 same-platform / 6 cross-site; merge precision 42/48 = 87.5% (75–94%); freshness by source.
- §3: fair-price method (stated area only, grouped folds, 44.5/31.1/24.4% tiers), Table 3 with intervals, by-source gain, area model dropped, weights table with signed coefficients, clipped-zero explanation.
- §5: Table 5 with nearest-first and price+closeness, bootstrap sentence, Table 6 with n, Wilson intervals and a Facebook row (23/25), caveats in the captions.
- §6–8: discussion, lessons (the leak), limitations (duplicates, scope, ward-level distance, pseudonymisation, AI labels), conclusion, a duplicate-detection recommendation, glossary.
- **App change made for the "price hint" rule:** `src/recsys/app.py` shows "cheaper/dearer by x%" only when the gap is at least 25% (`HINT_MIN_GAP`, the measured error); smaller gaps read "within the usual range (±25%)". App smoke test: no exception.
- **Known inconsistency (checked by viewing the images):** Figure 4 (`m4_price_model`) still shows the old bars 31.9% / 15.0% and "ML on the same rows: 20.6%", and Figure 2 (`m3b_dedup`) is titled "9,283 → 7,167 after merging cross-platform duplicates" with the old per-platform counts (Chotot −31, Rencity −10). Figures 3 (pipeline, built from the old MAPE), 7 (learned weights) and 9 (evaluation, no nearest-first bar) are probably stale too. The text and tables are correct, so **the PDF contradicts itself until Phase 5 regenerates the figures; do not circulate it before then.**

---

## Phase 4: Enhancements (new content)

| # | New section | Content (no code) | Length |
|---|---|---|---|
| 4.1 | **Related work** (new §2, after the Introduction) | Hedonic rent models; housing recommenders; learning to rank (pointwise logistic regression vs LambdaMART); how existing platforms (Nhatot, Mogi, Batdongsan) search and price. 8–12 new references. | 1 page |
| 4.2 | **Error analysis** (in the Evaluation section) | Price error by source, district and room type (table + one figure); the 10 worst predictions and why (free-text prices, whole houses, per-bed ads); a map of the residuals | 1–1.5 pages |
| 4.3 | **Ethics, privacy and legal considerations** | Decree 13/2023/NĐ-CP (pseudonymised vs anonymised data); robots.txt vs terms of service; Facebook data provenance and its limits; fairness of demoting female-only or sublet ads; what is stored and for how long | 1 page |
| 4.4 | **Uncertainty everywhere** | A CI for each headline metric; a short "how to read the intervals" paragraph | in place |
| 4.5 | **Reproducibility appendix** | Tables of the data snapshot date, software versions, model hyperparameters (400 trees, learning rate 0.05, L2 1.0, seed 0), fold scheme, personas, run order of the pipeline stages, in prose | 1 page |
| 4.6 | **Team contributions** (appendix) | Who did what. **You must supply this**; I will not invent it. | ½ page |
| 4.7 | **Statement on AI assistance** (front matter) | Where an AI assistant was used: code, labelling votes, drafting the report; and how the team checked its output | ¼ page |
| 4.8 | **Threats to validity**, expanded | Selection bias from hand-set candidates; 10-search bootstrap; cross-site duplicates remaining; ward-level geocoding | in place |
| 4.9 | Optional: **user pilot** | If 5+ people use the app for 15 minutes each: votes, a SUS questionnaire, quotes. Turns "no real users" into evidence. | 1 page |

Front matter, if you provide the details: supervisor, course code and name, and a signed declaration of originality.

---

**Status (2026-10-07): Phase 4 done, except 4.6 and 4.9, which need the team.** `report.pdf` is now 23 pages (backup `report_v4_before_phase4.tex.bak`). `.venv` → **92 passed**.

| # | Result |
|---|---|
| 4.1 | New §2 "Related work": hedonic pricing (Rosen 1974, Malpezzi 2003), gradient boosting (XGBoost, LightGBM), knowledge-based/hybrid recommenders (Burke 2002, Ricci et al. 2022), pointwise vs LambdaMART (Liu 2009, Burges 2010), position bias (Joachims et al. 2017), leakage (Kaufman et al. 2012), grouped CV (Roberts et al. 2017), Wilson 1927, existing services. **14 new references** (from memory; verify the page numbers before submission). |
| 4.2 | New §6.3 "Where the fair-price model fails": table by room type and price band, district range, the 100 worst cases (all over-estimates) and their causes. Numbers from the new `errors` section of `report_numbers.json`. The residual-map and by-segment figures are left to Phase 5. |
| 4.3 | New §9 "Ethical, legal and privacy considerations": Vietnam's PDPL (Law 91/2025/QH15, in force 1 Jan 2026, replaces Decree 13/2023; verified online), pseudonymisation, masking, names still in text, no retention period, robots.txt ≠ terms of service, Facebook collected by a Claude Code agent, the logged-in link check, fairness (female-only not learned; sublets demoted; hint threshold), AI use. |
| 4.4 | "Reading the intervals" paragraph in §6.1; intervals were already on every headline number. |
| 4.5 | Appendix B "Reproducibility": pipeline order in prose plus a settings table (snapshot, software versions, filters, duplicate rule, hyperparameters, folds, bootstrap counts, ranker rules, hint threshold, the 10 rated searches, sample seeds). |
| 4.6 | **Not done: team contributions need the team.** |
| 4.7 | "Statement on the use of AI assistance" after the executive summary. |
| 4.8 | Threats expanded: 10-search bootstrap, remaining cross-site copies across folds, ward-level coordinates, the AI rater's own preference. |
| 4.9 | Not done (user pilot needs people). |

**Found and fixed during 4.2: district labels.** Mogi wrote "Quận X" and the others "X", so **the app's district filter dropped every Mogi room** and the baseline was split. `prepare.unify_districts` + `sample_schema.short_district`, with tests. All report numbers updated (MAPE 25.4% vs 34.3%; 7,166 rooms; 7 cross-site); see `RECSYS_FINAL_REPORT.md` §10.9.

## Phase 5: Figures

Regenerate with `python -m src.recsys.make_slide_figures` and copy into `docs/latex/figures/`.

| Figure | Change |
|---|---|
| m2_data_sources | Add a "dated share" panel |
| m3b_dedup | Split same-platform vs cross-platform |
| m4_price_model | New numbers; colour by stated vs imputed area |
| m6_ranker_learned | Signed standardised coefficients with error bars, instead of clipped weights |
| m7_evaluation | Add the nearest-first bar; keep the "AI labels, old data" caption |
| **new** error_by_segment | MAPE by source, district and type (Phase 4.2) |
| **new** residual_map | Map of price residuals, crediting "© OpenStreetMap contributors" |
| m1_pipeline | Feedback arrow dashed, labelled "designed" |

Each figure needs a caption that stands alone, axis units (VND/month, m², km), and readable greyscale output.

---

**Status (2026-10-07): Phase 5 done.** New `src/recsys/make_paper_figures.py` writes 8 vector PDFs to `docs/latex/figures/` (Latin Modern, colour-blind-safe, panel labels, intervals); the pipeline, ranker and metric diagrams are TikZ. Two new figures (error by segment, residual map). Captions rewritten; "one room per building" corrected in §3.5 (the app shows all rooms; the CLI can cap). `report.pdf`: 25 pages, no overfull boxes, no unresolved references. Each figure was rendered and inspected. Details in `docs/FIGURE_REVIEW.md`. **Not done:** the slide figures still carry old numbers.

## Phase 6 (optional, highest value): real feedback

1. Deploy the app locally or on Streamlit Cloud with `RECSYS_FEEDBACK_DB` pointing to a fresh database.
2. Recruit 5 or more classmates. Each person runs 2 searches and votes on about 20 rooms, which reaches 200 votes from 5 sessions.
3. Train with `python -m src.recsys.ltr` without `--force`; it publishes only if the learned weights win on held-out searches.
4. Replace the AI-label results in Table 5 and Figure 9. Keep the AI-label results as a secondary comparison.

---

## Phase 7: Build and quality checks

| Check | How |
|---|---|
| Compiles cleanly | `tectonic report.tex` in `docs/latex`; no undefined references or overfull boxes over 10 pt |
| Numbers consistent | Every number in the PDF appears in `RECSYS_FINAL_REPORT.md` §10; cross-check with a script over the extracted PDF text |
| No code shown | No verbatim or listing blocks, no file paths or commands in the body (the appendix may name tools) |
| Visual check | Render all pages to PNG and inspect: title page, contents on one page, figures readable, no widow headings |
| Claims audit | Re-read `COUNTER_REPORT.md`; mark each item fixed, rebutted with evidence, or accepted as a limitation |
| Length | Target 20–24 pages, up from 16 |
| Docs in sync | Update `SLIDES_SCRIPT.md` and `SLIDES_PLAN.md` with the new numbers |

---

**Status (2026-10-07): Phase 7 done.**

| Check | Result |
|---|---|
| Compiles cleanly | Yes (Tectonic/XeLaTeX): no errors, no overfull boxes, no unresolved references; Tables 1, 2 and 8 set ragged-right |
| Numbers consistent | 42 of 43 headline numbers found verbatim against `report_numbers.json`; the 43rd is 1.36 vs 1.35 M (1,355,000 rounded half-up), so correct. No stale numbers (9,283, 7,167, 33.8%, 31.9% …); the two remaining "15.0%" are the deliberate history of the correction |
| No code shown | No paths, commands or code in the body; the `force` option is no longer in typewriter type |
| Visual check | All 24 pages rendered and inspected: title page, contents on one page, lists on one page (short captions added), figures and tables readable |
| Claims audit | `COUNTER_REPORT.md` §7: every point Fixed or Accepted; Open: team contributions and supervisor, real-user feedback |
| Length | **24 pages** (target 20–24) |
| Docs in sync | `SLIDES_SCRIPT.md` and `SLIDES_PLAN.md` rewritten as v6 (backups `.bak-2026-10-07`); slides now use the report's figures via `docs/slides/make_slide_pngs.py` → `docs/slides/figures/paper/` |
| Tests | `.venv` → **92 passed**; Streamlit AppTest: no exception |

**Still needed from the team:** team contributions (4.6), supervisor and course details, checking the 14 new references' page numbers, and real-user votes (Phase 6).

## Order and effort

| Step | Depends on | Effort |
|---|---|---|
| Phase 0 | — | you: a few minutes |
| Phase 1 (1.1–1.7) | 0 | ~half a day |
| Phase 2 | 1 | ~2 hours, plus labelling 50 duplicate pairs and 25 Facebook links (~1 hour by hand) |
| Phase 3 | 2 | ~2 hours |
| Phase 4 (4.1–4.5, 4.7, 4.8) | 2 | ~half a day |
| Phase 5 | 2 | ~1 hour |
| Phase 7 | 3–5 | ~1 hour |
| Phase 6 | app deployed | 1–3 days, depending on people |

**Needed from you:** (1) unblock scikit-learn (0.1); (2) approval to delete the raw-phone files (1.8); (3) the scope decision on whole houses (1.3); (4) team contributions, supervisor and course details (4.6); (5) whether to run the user pilot (4.9 / Phase 6).
