# Vietnam Rental Room

Academic data-science pipeline for Vietnamese rental-room (**phòng trọ**) listings:
crawl classifieds → clean/dedupe → geocode → features → EDA → map-based recommender.

`docs/PLAN.md` is the authoritative roadmap and canonical schema. `CLAUDE.md` has the
full architecture reference, per-source conventions, and non-negotiable crawling/PII
rules; read that before making changes.

## Repository layout

```
src/crawl/        network-facing crawlers (Fetcher, spiders, orchestrators) — mogi, alonhadat
src/parse/        pure HTML -> canonical dict parsers, no network calls
src/clean/        Parquet in, Parquet out: text clean, outliers, amenities, dedup
src/export/       Parquet -> CSV/Excel, and the flat "sample" schema exporters
src/geo/          address parsing + Nominatim geocoding client
src/recsys/       Hanoi rental recommender: data prep, ML fair-price / text models, feedback + learning to rank, CLI, Streamlit app, evaluation
src/pipelines/     unified dataset build + cross-source merge
src/scrapers/      additional third-party source scrapers (PhongTot, Rencity, YourHome)
config/            per-site crawl policy (sources.yaml)
docs/              per-source scraping writeups, crawling/technical/EDA reports
reports/           generated cleaning reports and figures
tests/             golden-fixture parser tests, no network

crawlers/          independent, self-contained crawler prototypes for other sources
  chotot/            Chotot Hanoi crawler (notebook-based)
  phongtro123/        phongtro123 crawler + parser + spatial-analysis pipeline
  facebook/           Facebook rental-groups scraper + parser
```

The core pipeline (`src/`, `config/`, `docs/`, `tests/`) implements the mogi and
alonhadat sources end to end, following the crawl/parse/clean layering documented in
CLAUDE.md. Each folder under `crawlers/` is a separately-authored, self-contained
project for one more source; none of them share code with the core pipeline or with
each other, so each has its own `requirements.txt` and should be run from its own
directory.

## Status

- **mogi.vn, alonhadat.com.vn** — complete crawlers on the shared architecture, nationwide.
- **Phase 3 cleaning** — built and validated on mogi; alonhadat rows flow in automatically.
- **Hanoi flat CSVs** (`sample.csv` + `*_hanoi_extracted.csv`) — cleaned, deduplicated,
  geocoded via `src/clean/run_clean_hanoi_csv.py`.
- **Recommender** (`src/recsys/`) — filters + weighted score with an ML fair-price model, text search and feedback-based weight learning, over the unified Hanoi dataset
  (`data/unified_hanoi_rentals.csv`, from the `unified-crawl-data` branch); CLI and Streamlit
  map app. Evaluation so far is model-rated, not human-rated; see "Recommender" below.
- **chotot, phongtro123, facebook** (`crawlers/`) — independent prototypes for
  additional sources, not yet folded into the shared crawl/parse/clean architecture.
- **batdongsan** — Hanoi-only prototype, marked **cut** in `docs/PLAN.md` (Cloudflare
  challenge even on robots.txt); see CLAUDE.md before running or extending it.

## Setup

```bash
pip install -r requirements.txt
```

See CLAUDE.md for the full command reference (crawling, reparsing, cleaning, exporting,
tests) and the crawling-conduct / PII rules that apply to every source in this repo.

## Recommender

ML recommender for Hanoi rentals. Stage 1: hard-constraint filters. Stage 2: a ranker whose score is a weighted sum of
price fit, ML fair-price "value", closeness, amenities and three data-quality signals; the **weights are learned** from
👍/👎 votes by logistic regression (learning to rank). Free-text search uses TF-IDF. **Status:** the deployed weights were
learned from 250 votes given by an AI assistant (`data/recsys_feedback_ai.sqlite`) and published with `--force`, because
they are *not* shown to beat the hand-set weights (held-out NDCG@10 0.83 vs 0.85, difference not significant). The app lets
you switch to the hand-set weights ("Cách xếp hạng"); CLI: `--ranker hand`. Replace the learned weights with ones trained on
real user votes as soon as there are enough.

Needs `data/unified_hanoi_rentals.csv` (copy `data/` from the `origin/unified-crawl-data` branch). Run from the repo root:

```bash
pip install -r requirements.txt                # streamlit, folium, streamlit-folium, scikit-learn
python -m src.recsys.prepare                   # ~1-2 min: geo repair (cached Nominatim), drop un-locatable /
                                               # out-of-Hanoi rows, hash phones, post dates, cross-platform
                                               # dedup, ML area + fair price -> data/unified_hanoi_rentals_dedup.csv
python -m src.recsys.price_model --report      # cross-validated errors of the ML models vs simple baselines

# CLI
python -m src.recsys.recommend --budget 4000000 --district "Cầu Giấy" --need air_conditioner --top 10
python -m src.recsys.recommend --budget 3000000 --university NEU --max-uni-km 2   # --help for all filters

# Streamlit app (opens http://localhost:8501)
streamlit run src/recsys/app.py

python -m src.recsys.ltr                       # learn weights from real 👍/👎; publishes only with >= 200 votes / 5 sessions and a held-out win
python -m src.recsys.ltr --db data/recsys_feedback_ai.sqlite --force   # what is deployed now: AI-labelled votes, published even without a win
python -m src.recsys.evaluate                  # persona table + real-feedback metrics -> docs/RECSYS_EVAL.md
python -m pytest tests -q
```

How to use / check the Streamlit app (layout follows listing sites such as yourhome.top):

1. Start it and open the URL it prints (first load ~20 s: data, models and the text index are built once).
2. **Sidebar** — *Tìm theo mô tả* (free text, e.g. "gác xép, ban công"), *Khoảng giá*, *Loại phòng*, *Diện tích*,
   *Tiện nghi*, *Quận*, *Gần trường đại học* (distance to that campus, default ≤ 3 km), *Đăng trong vòng* (only ~30% of
   ads have a date; undated ones are kept), *Nguồn tin*, and a checkbox for shared-room/slot ads. The filters are copied
   into the page URL, so copying the address shares the search.
3. **Trang chủ** — "N kết quả phù hợp", *Sắp xếp*, *Hiển thị* (8–100 per page), "Trang x/y". Each card: photo, type,
   price, an ML hint ("Rẻ hơn ~12% so với phòng tương tự"), area (`~` = estimated), district, post age, *Xem tin*,
   *Bản đồ*, photo gallery, and four buttons: 👍 / 👎 (feedback, stored locally in `data/recsys_feedback.sqlite`),
   ♡ (save) and ≈ (similar rooms, shown in a panel at the top).
4. **Bản đồ** — rooms as soft-coloured price labels (green < 3 triệu, blue 3–5, rose > 5); grey numbered discs zoom in
   when clicked. Pick a *Bán kính* and click a point: the map glides there and lists rooms inside, nearest first.
   Switch on *Hai điểm* to click two points (e.g. school and work): only rooms within the radius of both are listed.
5. **Đã lưu (n)** — saved rooms and a side-by-side comparison of up to 4 (price, ML fair price, area, district,
   distance to centre, amenities, post age).
6. **Privacy** — no phone numbers anywhere: `prepare` hashes them with the project salt (`src/crawl/pii.py`) and drops
   poster names; contact the landlord through the original ad. Facebook posts show no photos.
7. Headless smoke test: `python -c "from streamlit.testing.v1 import AppTest; at=AppTest.from_file('src/recsys/app.py', default_timeout=240).run(); print(at.exception)"` should print an empty list. Set `RECSYS_FEEDBACK_DB=<temp file>` when testing so test clicks do not end up in the real feedback.

Known limits: no real feedback has been collected yet, so the weights are still hand-set and the only quality ratings
are AI-assigned; many coordinates are ward-level. See `docs/RECSYS_FINAL_REPORT.md`.

## Data & PII

`data/` is gitignored; the crawled corpus is reproducible-but-expensive local state.
Every crawler must hash phone numbers/poster identities before they reach a parsed row
or exported file (see `src/crawl/pii.py`). Raw scraped exports (root CSVs, and anything
under `crawlers/*/data/`) are never committed — see `.gitignore` and the "Data & PII on
disk" section of CLAUDE.md.

Geocoding uses the public Nominatim API under its usage policy (≤1 req/s, cached,
identifying User-Agent); "© OpenStreetMap contributors" is credited wherever the
resulting coordinates are published.
