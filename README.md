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
src/recsys/       Hanoi rental recommender: CLI, Streamlit map app, dedup/geocode repair, evaluation
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
- **Recommender** (`src/recsys/`) — filters + weighted score over the unified Hanoi dataset
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

Needs `data/unified_hanoi_rentals.csv` (copy `data/` from the `origin/unified-crawl-data`
branch). Run from the repo root:

```bash
pip install -r requirements.txt                # includes streamlit, folium, streamlit-folium
python -m src.recsys.regeocode_fallback        # one-off: ~35 cached Nominatim requests, repairs a fallback coordinate
python -m src.recsys.dedup_unified             # ~70 s: cross-platform duplicates -> data/unified_hanoi_rentals_dedup.csv

# CLI
python -m src.recsys.recommend --budget 4000000 --district "Cầu Giấy" --need air_conditioner --top 10
python -m src.recsys.recommend --budget 3000000 --university NEU --max-uni-km 2   # --help for all filters

# Streamlit app (opens http://localhost:8501)
streamlit run src/recsys/app.py

python -m src.recsys.evaluate                  # persona evaluation -> docs/RECSYS_EVAL.md
python -m pytest tests -q
```

How to check the Streamlit app by hand:

1. Start it with the command above and open the URL it prints. The first load takes a few seconds.
2. Defaults (budget 4M) should show a map with numbered markers, a table next to it and a
   caption under the map; the sidebar filters change both together.
3. Try: budget slider down to 1.0 (few or no results; a warning appears when nothing matches);
   pick a *Quận*; pick a *Gần trường* (a distance slider appears); tick two amenities;
   untick/tick "Hiện ga metro và trường đại học" (green cap = university, purple dot = metro);
   tick "Cả tin ở ghép / slot" (cheap per-bed ads come back).
4. Click a marker for the popup (price, area — `~` means estimated — and a link to the ad);
   rank numbers in the tooltip should match the table order.
5. A few listings have no coordinates: they appear in the table but not on the map (the caption says how many).
6. Stop with Ctrl+C. Headless smoke test: `python -c "from streamlit.testing.v1 import AppTest; at=AppTest.from_file('src/recsys/app.py', default_timeout=120).run(); print(at.exception)"` should print an empty list.

Known limits: ratings used so far were assigned by the assistant, not by people; coordinates are
ward-level for many listings; see `docs/RECSYS_UPDATE_REPORT.md` and `docs/RECSYS_RATING_STUDY.md`.

## Data & PII

`data/` is gitignored; the crawled corpus is reproducible-but-expensive local state.
Every crawler must hash phone numbers/poster identities before they reach a parsed row
or exported file (see `src/crawl/pii.py`). Raw scraped exports (root CSVs, and anything
under `crawlers/*/data/`) are never committed — see `.gitignore` and the "Data & PII on
disk" section of CLAUDE.md.

Geocoding uses the public Nominatim API under its usage policy (≤1 req/s, cached,
identifying User-Agent); "© OpenStreetMap contributors" is credited wherever the
resulting coordinates are published.
