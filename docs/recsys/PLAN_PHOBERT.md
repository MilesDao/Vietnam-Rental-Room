# Plan — testing PhoBERT as the text model (7 Oct 2026)

**Why.** The instructor asked for a comparison with state-of-the-art methods. For the *tabular* part we already compared with XGBoost, LightGBM and
CatBoost (report §4.5): same error, so the library does not matter. The *text* is what gives the gain (about 3 points), and our text model is
the classical TF-IDF + SVD. The state of the art for Vietnamese text is PhoBERT (Nguyen & Nguyen, Findings of EMNLP 2020, pp. 1037–1042;
`vinai/phobert-base-v2`, 135M parameters, RoBERTa-base architecture, 256 tokens, word-segmented input). This plan tests whether a pre-trained
Vietnamese language model beats TF-IDF + SVD *inside the same pipeline and the same folds*.

**Question and hypotheses.** Does PhoBERT lower the grouped-CV MAPE of 22.6% (tabular only: 25.4%)?
- H1 (frozen): PhoBERT embeddings + gradient boosting ≈ TF-IDF + SVD (within ±1 point). Reason: ads are short, formulaic and keyword-driven
  ("full đồ", "vsc", "cho nữ"); the signal is lexical, so contextual embeddings may add little.
- H2 (fine-tuned): fine-tuning on the rent gives a small gain (0–1.5 points) at most, and the result is worse on groups with few rooms.
- Either outcome is reported. The lesson (*complexity does not beat the right features at this size*, or the opposite) is a result.

## Design: three stages, each with a decision gate
| Stage | What | Cost | Gate |
|---|---|---|---|
| **A. Frozen embeddings** | PhoBERT-base-v2 (no training) → mean-pooled 768-d vector of title + first 600 characters → reduce to 64 components (PCA, fit in-fold) → join the tabular features → the same histogram gradient boosting. Variants: PhoBERT alone; PhoBERT + TF-IDF SVD (both). | one forward pass over 6,866 texts, about 1–3 min on the GPU, 15–30 min on the CPU | if A is no better than TF-IDF (diff interval contains 0 or is worse), report it and stop at A unless you want B |
| **B. Fine-tuning** | PhoBERT + a regression head on log rent (text only, or text + the tabular prediction as input), grouped 5-fold, same folds; AdamW, learning rate 2e-5, 3 epochs, max length 128, fp16, batch 16; out-of-fold prediction used (a) alone and (b) as a feature of the boosting model | 5 trainings × ~5–10 min on the RTX 2050 (4 GB) with fp16; needs gradient checkpointing if memory is short | run only if A shows promise (diff interval below 0) or the instructor insists |
| **C. Held-out test** | the winning variant refitted on the 5,514 development rooms, scored once on the 1,352 locked rooms (same split, seed 0) | minutes | always, for whatever is reported as "best" |

## Leakage guards (as in the main study)
1. **Digits removed** before tokenisation (same `text_of`), so the model cannot read "2,5 triệu". Repeat the unit-word check (remove "triệu", "tr",
   "k"...) for the winning variant; the earlier check changed the error by only +0.13 points.
2. **Folds**: the same `price_model._splits` (all ads of one poster, or within 50 m, in one fold). Frozen embeddings use no labels, so they may be
   computed once for all rooms; fine-tuning must be redone per fold with the test fold never seen.
3. **Out-of-fold only**: any feature built from a fine-tuned model is produced out-of-fold; the held-out test rooms never enter a fold.
4. **No label in the text pipeline**: the PCA is fit on training rows only.

## Practical issues
- **Word segmentation.** PhoBERT was trained on text segmented by VnCoreNLP's RDRSegmenter, which needs **Java** (not installed here). Options:
  (i) `pyvi` or `underthesea` (pure Python; slightly different segmentation than in pre-training: say so); (ii) install a JRE and use
  `py_vncorenlp` (exact, but a system-level install). *Plan: start with pyvi; if the gain is borderline, rerun with VnCoreNLP.* Also test
  unsegmented input as a sensitivity check.
- **Software.** `torch` (CUDA build, about 2.5 GB), `transformers`, `pyvi`. Weights `vinai/phobert-base-v2` are downloaded from Hugging Face
  (about 0.5 GB). Disk is no problem (178 GB free).
- **Hardware here.** NVIDIA RTX 2050, 4 GB; 15.7 GB RAM; 12 CPU cores. Texts are short (mean 258 characters, about 56 words, so about
  70–100 tokens): inference is cheap; fine-tuning fits with fp16 and batch 16.
- **Reproducibility.** Fixed seeds; save embeddings to `data/interim/phobert_emb.npy` (gitignored); one script `src/recsys/phobert_models.py`
  writing `docs/report_numbers.json["phobert"]`.

## Deliverables
1. `src/recsys/phobert_models.py` (stages A–C) and a test that digits are removed and folds are the grouped ones.
2. Report: a row (or two) in §4.5, renamed "Comparison with state-of-the-art models" with a short paragraph on PhoBERT; one new reference
   (Nguyen & Nguyen 2020); update the executive summary, the related-work sentence on deep models, the discussion and the limitation "deep
   networks were not tried". Page budget: +0.2 page (report stays about 16 pages).
3. Slides: slide 4 table (the "deep networks / transformers" row changes from *no* to the result), slide 8 table (a PhoBERT row), slide 14
   lessons; `EXAM_PREP.md` question on PhoBERT.
4. A `docs/COUNTER_REPORT_V2.md` entry with the result and its limits.

## What would count as a fair conclusion (decided in advance)
- **PhoBERT better by more than the noise** (paired cluster-bootstrap interval below zero): adopt it only if the gain is at least about 0.5 points
  *and* it holds on the held-out test; say that it costs a GPU and a download.
- **No difference**: keep TF-IDF + SVD (cheaper, transparent, no extra dependency), and report PhoBERT as evidence that the text signal is lexical.
- **Worse**: report it, with the likely reasons (short text, domain slang, segmentation mismatch).
Do **not** tune PhoBERT on the test rooms, report only the best of many runs, or change the folds.

## Schedule (about half a day)
| Step | Time |
|---|---|
| Install `torch`, `transformers`, `pyvi`; download the weights; smoke test on 20 texts | 30 min |
| Stage A: embeddings, three variants, grouped CV, intervals | 1 h |
| Stage C for A (held-out test) and the unit-word check | 30 min |
| Stage B (only if A passes the gate): fine-tune 5 folds | 1.5–3 h |
| Report, slides, exam prep, tests | 1 h |

## Needs your approval before I start
1. Downloading and installing `torch` (about 2.5 GB), `transformers`, `pyvi`, and the PhoBERT weights (about 0.5 GB) from Hugging Face.
2. Segmentation: start with `pyvi` (no Java), or install Java for the exact VnCoreNLP segmenter.
3. Stage B: run only if stage A shows promise, or always (about 2–3 hours of GPU time).

## Status (7 Oct 2026): stage A done; gate not passed, so stage B (fine-tuning) was not run
Setup: `torch` 2.6.0+cu124, `transformers`, `pyvi`; weights `vinai/phobert-base-v2` (135M parameters); RTX 2050 (4 GB): embedding 6,866 texts takes about
20 s; mean text length 81 tokens (maximum 183, below the 256 limit). Digits are removed before tokenisation (asserted in the script and tested).

| Variant (same rooms, same grouped folds, same boosting model) | MAPE (95% interval) | Difference from TF-IDF SVD (95% interval) |
|---|---|---|
| tabular only | 25.4% (24.2–26.8) | +2.79 (+2.13 to +3.42) |
| **TF-IDF SVD (final model)** | **22.6% (21.6–23.8)** | — |
| PhoBERT frozen, pyvi segmentation, PCA 64 | 22.9% (21.8–23.9) | +0.22 (−0.30 to +0.66) |
| PhoBERT frozen, unsegmented | 23.1% (22.1–24.3) | +0.47 (+0.04 to +0.88) |
| PhoBERT + TF-IDF SVD | 22.5% (21.4–23.6) | −0.14 (−0.42 to +0.12) |

H1 is confirmed: frozen PhoBERT is no better than TF-IDF (the interval contains zero); segmentation helps slightly; the combination is not
distinguishable either. By the rule decided in advance (adopt only a gain of at least about 0.5 points that also holds on the held-out test) the
final model stays TF-IDF + SVD, and stage C is not needed. Stage B was not run (gate: stage A showed no promise); fine-tuning might behave
differently and this is stated as untested. Code: `src/recsys/phobert_models.py`, tests: `tests/test_phobert.py`; results:
`docs/report_numbers.json["phobert"]`; report §4.5 (Table 5) and reference [9].
