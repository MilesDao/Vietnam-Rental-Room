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

How to use / check the Streamlit app (layout follows listing sites such as yourhome.top):

1. Start it with the command above and open the URL it prints (first load takes a few seconds).
2. **Trang chủ view** — left sidebar filters: *Khoảng giá*, *Loại phòng*, *Diện tích*, *Tiện nghi*, *Quận*,
   *Gần trường đại học*, *Nguồn tin*, and a checkbox to include shared-room/slot ads. Above the cards:
   "N kết quả phù hợp", a *Sắp xếp* box (Phù hợp nhất = the recommender score, giá, diện tích, gần trung tâm) and
   a *Hiển thị* box (8 / 12 / 24 / 48 / 100 tin per page). Each card shows photo, type badge, price, area, address,
   **Xem tin** (opens the ad), **Bản đồ** (small popup map of that room) and **Ảnh & liên hệ** (up to 5 photos and, when the data has one, the phone number with a copy button). Use « ‹ › » for "Trang x/y".
   Changing any filter returns to page 1.
3. **Bản đồ view** (switch at the top) — every room matching the filters is a soft-coloured price label ("3,5tr";
   green < 3 triệu, blue 3–5, rose > 5); nearby rooms merge into grey numbered discs. **Click a number**: the map glides
   and zooms into the area those rooms cover (rooms on the exact same spot fan out instead). Pick a *Bán kính*
   (0.5–10 km) and **click an empty point**: the map glides there (from where you were looking, or from the whole city the
   first time), a dashed teal ring gently "breathes", and the rooms inside are listed below, nearest first;
   Click a **price label** to open a popup with photos (click a thumbnail to enlarge it), the key facts, a link to the original ad and, when available, a *Hiện số điện thoại* button that reveals the number. *Xóa điểm đã chọn* resets it. Zoom steps are fractional (0.25) so scroll/+/- zooming is smooth. At most 5000 rooms are drawn.
4. Checks worth doing: price range 0.5–1 triệu (few results), 20–25 triệu (few results), a *Quận*, a *Gần trường*,
   a different *Hiển thị* size, then page forward; click the map twice at different places.
5. **Phone numbers / privacy.** Only numbers already present in the data are shown, and only about 4,900 listings
   have one (Phongtro123 mostly; the rest hold a hash or nothing). Facebook posts never show a photo or a number
   (personal data, `docs/PLAN.md` Phase 2B). Numbers are never put in the results table or any export. They do sit
   in the map page's data for the rooms drawn, so do not screenshot or share the app publicly. This goes against the
   project's rule that raw numbers must be hashed at ingest (the branch data already contains them): start the app
   with `RECSYS_SHOW_PHONE=0` (e.g. `RECSYS_SHOW_PHONE=0 streamlit run src/recsys/app.py`; PowerShell:
   `$env:RECSYS_SHOW_PHONE=0`) to hide them.
   A few listings lack coordinates:
   they appear in the list but not on the map. Not implemented vs. yourhome.top: the two-point search, the poster-type
   filter (replaced by *Nguồn tin*), "newest first" (most listings have no post date) and lease-expiry dates.
6. Stop with Ctrl+C. Headless smoke test: `python -c "from streamlit.testing.v1 import AppTest; at=AppTest.from_file('src/recsys/app.py', default_timeout=240).run(); print(at.exception)"` should print an empty list.

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
