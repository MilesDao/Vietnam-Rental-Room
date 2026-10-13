# Exam preparation — Estimating Fair Rents of Rooms in Hanoi

One page of key numbers, then hard questions with answers. Every number is in `docs/report_numbers.json`; report sections in brackets
(report: `docs/latex/report.pdf`, 15 pages; PhoBERT is NOT in the report (result only in PLAN_PHOBERT.md and the slides); sections: 4.5 'Application' = XGBoost/LightGBM/CatBoost, 4.6 held-out test, 4.7 drivers, 4.9 unseen sources, 4.10 band).

## Key numbers (memorise these)
| What | Number | Where |
|---|---|---|
| Listings → distinct rooms | 9,281 → 7,166 (2,115 duplicates; 7 cross-site) | §3.3 |
| Training rooms | 6,866 (300 shared / per-bed offers set aside) | §4.1 |
| Rent (EDA) | median 4.0 M, IQR 3.1–5.0, range 0.5–50; skewness 3.7 → 0.34 on log | §3.5 |
| Rent vs area | r = 0.62 (log–log, 3,539 rooms with area); 48.5% without area | §3.5 |
| Distance to centre vs rent | Spearman −0.22; metro / university ≈ 0 | §3.5 |
| Baseline (median of type × district) | MAPE 34.3% (32.4–36.2) | Table 4 |
| Best tabular models | 25.0–25.4% (random forest, gradient boosting) | Table 4 |
| **Final model (gradient boosting + digit-free text)** | **MAPE 22.6% (21.6–23.8); median 15.7%; R² 0.57; 70% within ±25%** | Table 4 |
| Text also helps the random forest | 25.0% → 23.6% | §4.4 |
| **PhoBERT (frozen, same folds)** | 22.9% vs TF-IDF 22.6% (+0.22, −0.30 to +0.66); both 22.5%; unsegmented 23.1% | §4.5 |
| **SOTA libraries (same folds)** | with text: LightGBM 22.7%, XGBoost 22.7% (diff +0.02, +0.05, n.s.), CatBoost 23.4% (+0.73); no text 25.1–25.8% | §4.5 |
| **Held-out test (1,352 rooms locked away)** | **22.8% (20.9–24.8) vs baseline 34.5%** — same as CV, no selection bias | §4.6 |
| Leaks | 15.0% (area estimated from rent) → 21.5% (price in title) → 22.6% honest | §4.2 |
| Tuning | 25.4% → 25.1% (nested, not significant) | §4.5 |
| Importance | area +9.2 (permuted) / +4.3 (removed); distances: +2.0 permuted but −0.1 removed (district explains 84% of distance) | §4.7 |
| Words | shared bathroom, "cho nữ", basic furniture → lower; private washer, "căn" → higher; removing price-unit words: +0.13 (n.s.) | §4.7 |
| Noisy titles | 480 flagged (7%); final model 31.7% vs 22.0% on the rest; training on clean: no gain (−0.12) | §4.8 |
| Leave a source out (final model) | beats baseline on all 7: Facebook 32.7% vs 39.4%; Rencity 23.8% vs 25.3% (just). Without text: fails on Facebook (39.9) and Rencity (26.3) | §4.9 |
| Intervals | raw 80% → 68%; **conformal calibration (+8% margin) → 80.0%**; 9.6% below, 10.5% above | §4.10 |
| AI-rated ranking | learned 0.835, hand-set 0.851, nearest 0.823, random 0.722 | Table 8 |
| Simulation | recovery r = 0.99 / 0.94; gain over the formula small even at 1,600 votes (+0.012 n.s. / +0.026) | §6.3 |
| Duplicates check | 85.7% (72–93) of same-site merges correct; 6/6 cross-site | §3.3 |
| Links | 96–100% (25 per source); Facebook 23/25 | Table 9 |

## Hard questions
1. **Why log of the rent?** Skewness 3.7 on the rent, 0.34 on its log; errors matter in relative terms.
2. **Why MAPE and not RMSE?** It is in percent, which users understand; we also report the median error, MAE and R².
3. **What exactly is a grouped fold?** All ads with the same phone hash, or within ~50 m, go to the same fold, so no near-copy is split.
4. **What is the first leak?** Missing areas were filled with an estimate made from the room's own rent; the price model then saw the rent.
5. **What is the second leak?** 52% of titles state the rent; the TF-IDF could read it. We delete every digit before using the text.
6. **Couldn't words still leak?** Unit words ("triệu", "tr", "k") survive; removing them too changes the error by +0.13 points, interval
   −0.20 to +0.50, so they do not drive the gain.
7. **You chose the best of 11 models on the same folds — isn't that optimistic?** We locked 20% of groups away first; the model chosen on the
   other 80% scores 22.8% on the test rooms, the same as in CV.
8. **Why nested tuning?** Choosing settings on the folds that score them is optimistic; we tune inside each training fold only.
9. **Permutation says distance matters, ablation says no — which is right?** Both: the district explains 84% of the distance; scrambling
   distance creates impossible rooms, removing it lets the district take over.
10. **Does the model work on a source it never saw?** Yes, on all seven, thanks to the text; without the text it fails on Facebook (older,
    free-text posts, 74% without area) and Rencity (no area at all). Rencity's gain is small (interval −2.9 to −0.1).
21. **Which model do the importance plots use?** The model without text (25.4%): its inputs form groups that can be scrambled or removed;
    the text is analysed separately (which words matter, +2.8 points).
11. **How is the usual-price band built?** Centred on the fair price, width from a 10/50/90% quantile model, then widened by a cross-conformal
    margin (≈8%) so it contains 80% of rents out of sample.
12. **What does "fair price" mean?** The rent the model expects for a room like the one described, learned from other rooms; not a valuation.
13. **Did you try PhoBERT / deep learning? Did you compare with SOTA?** PhoBERT: yes, as frozen embeddings in place of TF-IDF (pyvi segmentation, 64 PCA components, same folds): 22.9% vs 22.6% (difference +0.22, interval −0.30 to +0.66), 23.1% unsegmented, 22.5% with both (−0.14, −0.42 to +0.12). Fine-tuning was not run: the frozen result showed no sign of a gain, and we do not claim fine-tuning cannot help. Libraries: SOTA for tables = boosted trees: we ran XGBoost, LightGBM and CatBoost on the same folds (25.1–25.8% without text; with text LightGBM 22.7%, XGBoost 22.7%, CatBoost 23.4% vs our 22.6%: the differences are 0.02, 0.05 and 0.73 points). Deep networks on the table were not tried: 6,866 rooms and the benchmark by Grinsztajn et al. 2022 finds trees better at this size. TF-IDF + SVD already adds about 3 points.
14. **What does the EDA tell you?** Log target; area is the strongest correlate but half missing (models must handle NaN); type and district
    matter; distances weak.
15. **Is the recommender a real recommender?** Knowledge-based: hard filters + a weighted utility. Collaborative filtering does not fit
    rentals (unique items, rare searches).
16. **Why does the learned ranker not win?** 250 AI votes; and in the simulation even 1,600 votes give only a small gain, because the hand-set
    formula is already close to the users' tastes.
17. **What is the simulation, and what is it not?** Simulated users with known tastes rate random-order rooms; it tests the method, not real
    preferences. Its numbers move by ~0.02 with small input changes, so only the pattern counts.
18. **Privacy?** Salted hashes are pseudonyms (still personal data, Law 91/2025/QH15); numbers in text masked; data kept by the team.
19. **How did you use AI?** Permitted; Facebook collection, code, AI ratings, simulation, drafting. Every such result is labelled.
20. **What was the hardest bug?** The leaks; also the district-label bug that hid every Mogi room from the district filter, and placeholder
    coordinates 1,000 km from Hanoi.

## Demo checklist
`streamlit run src/recsys/app.py` → search "gác xép" → budget 2–5 M → pick a university → open a card (price hint) → "≈ similar" → map with
two points. Use `RECSYS_FEEDBACK_DB=<temp file>`.
