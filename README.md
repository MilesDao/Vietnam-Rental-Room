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

## Data & PII

`data/` is gitignored; the crawled corpus is reproducible-but-expensive local state.
Every crawler must hash phone numbers/poster identities before they reach a parsed row
or exported file (see `src/crawl/pii.py`). Raw scraped exports (root CSVs, and anything
under `crawlers/*/data/`) are never committed — see `.gitignore` and the "Data & PII on
disk" section of CLAUDE.md.

Geocoding uses the public Nominatim API under its usage policy (≤1 req/s, cached,
identifying User-Agent); "© OpenStreetMap contributors" is credited wherever the
resulting coordinates are published.
