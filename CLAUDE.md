# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Academic data-science pipeline for Vietnamese rental-room (**phòng trọ**) listings:
crawl classifieds → clean/dedupe → geocode → features → EDA → map-based recommender.
`docs/PLAN.md` is the authoritative 9-phase roadmap and canonical schema; **read the
relevant phase before starting new work** — it records source recon results, go/no-go
decisions per site, and the deduplication/ethics design. `docs/mogi_scraping.md` and
`docs/alonhadat_scraping.md` document those two sources end to end; new sources should
follow the same shape.

Current state:
- **Phase 2, mogi.vn and alonhadat.com.vn** — both complete and on the same
  architecture (frontier-of-slices crawler, `Fetcher`, `pii.py` hashing, Parquet output,
  resumable SQLite state). mogi is nationwide (32 provinces × 4 sub-categories);
  alonhadat is nationwide too (34 provinces × 1 category) but a much smaller corpus
  (~1,900 listings total vs. mogi's ~30k in HCMC alone). alonhadat serves a CAPTCHA
  under sustained crawling, and only 69 Hanoi listings came in before it did. Whether
  to keep crawling it very slowly or cut it like batdongsan is undecided; see
  `docs/alonhadat_scraping.md` §8.
- **Phase 3 cleaning** (`src/clean/`) — built, but validated over mogi only so far; output
  in `reports/cleaning_report.md`, which lists what's still missing (2025 admin-unit
  crosswalk, image-hash dedup, Tier-2 cross-post dedup, manual precision/recall).
  `load_interim()` picks up any `parsed_*.parquet`, so alonhadat rows flow in
  automatically once crawled — re-verify the report and dedupe thresholds once there's a
  real alonhadat run to look at, not just mogi's.
- **batdongsan** — a Hanoi-only prototype crawler that does *not* follow the mogi/alonhadat
  conventions and that PLAN.md marks **cut** (see "batdongsan (prototype, cut)" below).
- **Hanoi flat CSVs** (`sample.csv` + both `*_hanoi_extracted.csv`) — cleaned, deduplicated
  and geocoded by `src/clean/run_clean_hanoi_csv.py` into `data/processed/`; report in
  `reports/hanoi_csv_cleaning_report.md`. Geocoding the canonical Parquet (the rest of
  Phase 4) and Phases 5–9 (features, EDA, recsys, app) are not built.

Per `docs/PLAN.md` recon, source priority is Chotot (public JSON API) → phongtro123 →
alonhadat → mogi; batdongsan.com.vn is marked **cut** (Cloudflare challenge even on
robots.txt). Chotot and phongtro123 have no code yet.

## Commands

```bash
pip install -r requirements.txt
# batdongsan's BrowserFetcher also needs Playwright, which is NOT in requirements.txt:
#   pip install playwright && playwright install chromium

# Crawl mogi (resumable; Ctrl+C is a clean stop, re-run to continue)
python -m src.crawl.run_mogi --city hanoi --max-pages 1 --max-details 5   # smoke run
python -m src.crawl.run_mogi --city all --categories all                  # nationwide
python -m src.crawl.run_mogi --city hcmc,da-nang                          # some provinces

# Rebuild the Parquet from retained raw HTML (parser fix, salt rotation, hard kill)
python -m src.parse.reparse_mogi --dry-run

# Crawl alonhadat (same resumability/CLI shape as mogi; smaller nationwide corpus)
python -m src.crawl.run_alonhadat --city hanoi --max-pages 1 --max-details 5  # smoke run
python -m src.crawl.run_alonhadat --city all                                  # nationwide
python -m src.parse.reparse_alonhadat --dry-run

# Phase 3: data/interim/parsed_*.parquet -> data/processed/listings_clean.parquet
#          and rewrites reports/cleaning_report.md
python -m src.clean.run_clean

# Parquet -> Excel/QGIS-safe CSV (utf-8-sig, list columns joined on " | ")
python -m src.export.to_csv [--only-geocoded] [--no-description] [-o PATH]

# Raw HTML -> flat, human-browsable Hanoi-only CSV at the repo root (bypasses the
# Parquet; see "batdongsan (prototype, cut) and the 'sample' export" below)
python -m src.export.export_mogi_to_sample        # mogi_hanoi_extracted.csv
python -m src.export.export_alonhadat_to_sample   # alonhadat_hanoi_extracted.csv

# Clean those two + sample.csv and geocode missing coordinates (public Nominatim, cached
# in data/external/nominatim_cache.sqlite). --dry-run sends nothing and writes nothing.
python -m src.clean.run_clean_hanoi_csv --dry-run
python -m src.clean.run_clean_hanoi_csv [--no-geocode] [--max-requests N]
# --write-back also fills latitude/longitude/geo_confidence in the three root CSVs
# (a <name>.bak copy is kept). Re-running the exporters above overwrites them again.
python -m src.clean.run_clean_hanoi_csv --write-back

# Tests — offline
python -m pytest tests/ -v
python -m pytest tests/test_mogi_parser.py::test_parse_detail_page_fields -v
```

Run everything from the repo root (the `export_*_to_sample.py` scripts use CWD-relative
paths). The empty root `conftest.py` exists solely to put the repo root on `sys.path` so
`from src...` imports resolve under pytest — don't delete it. There is no
linter/formatter configured and no `pyproject.toml`.

The PII salt must stay constant for the whole corpus (`phone_hash` is the strongest
dedupe key). `src/crawl/pii.py` resolves it as `PROJECT_SALT` env var → repo-local
`.project_salt` (gitignored, auto-generated once) → generate. Don't rotate it without
re-running `reparse_mogi`.

## Architecture

Layered, with the network/pure boundary as the organizing principle:

- **`config/sources.yaml`** — per-site crawl policy (base URL, category paths, province
  slugs, pagination scheme, rate limit, retry policy, UA, `disallow` mirror). Behavior
  changes belong here, not in code: e.g. crawling another mogi category is a
  `category_paths` edit. `mogi` and `alonhadat` are fully populated; `batdongsan` is a stub.
- **`src/crawl/`** — everything that touches the network. `fetcher.py` (`Fetcher` =
  one host's crawl session: robots.txt enforcement, jittered delay, exponential backoff
  with jitter on 429/5xx, single `requests.Session`); `spiders/<site>.py` (discovery:
  walk list pages → deduped card rows); `run_<site>.py` (orchestrator).
- **`src/parse/`** — **pure functions of HTML text, no network calls.** That constraint is
  what makes golden-fixture tests possible; keep it. `<site>_parser.py` returns canonical
  dicts; `vn_text.py` holds shared Vietnamese number parsing (`parse_price_vnd`,
  `parse_area_m2`) meant for all sources.
- **`src/crawl/pii.py`** — salted SHA-256 (16 hex chars) + carrier prefix. Applies to
  *every* source, Tier 1 included. A raw phone number or poster identity must never reach
  a parsed row or an exported file; see the assertion in `test_parse_detail_page_fields`.
- **`src/clean/`** — Parquet in, Parquet out: `text_clean` (NFC, strip emoji/control
  chars, plus an `ascii_fold` copy for matching) → drop rows missing price/area →
  `outliers` → `amenities` (keyword lexicon with negation over folded text) → `dedup` →
  `pick_canonical`.
- **`src/export/`** — two unrelated output shapes (see "Prototype sources").
- **`src/clean/sample_schema.py`** — cleaning rules for the flat 31-column schema
  (`sample.csv` and the `*_to_sample` exports), a separate path from the Parquet pipeline.
  It flags rather than drops (every PhongTot row lacks a price, every Rencity row an area)
  and removes only same-platform duplicates. An address counts toward a duplicate match
  only if it names a house or alley number: street- and neighbourhood-level addresses
  ("Yên Xá, Xã Tân Triều") are shared by many different rooms.
- **`src/geo/`** — `address.py` (pure: address → alley/street/ward/district query
  candidates, plus a check that each result is the right kind of place with the right
  name) and `nominatim.py` (network: cached client, ≤1 request/s). OpenStreetMap has no
  district level in Hanoi since the 2025 reform; old districts and wards survive only as
  historic boundaries, so a district bounds the search box and never goes in the query
  text. Nominatim gives confident wrong answers (a different alley number, a company
  named after a ward), which is why no result is used unchecked.

### mogi crawl pipeline

`run_mogi.py` walks a **frontier of (province × category) slices** — 32 provinces × 4
phòng-trọ sub-category views from `config/sources.yaml` — interleaving discovery with
detail fetch → **gzip the raw HTML to `data/raw/html/<site>/<date>/`** → parse → buffer →
flush to `data/interim/parsed_<site>.parquet` every 200 rows (atomic tmp+replace, dedupe
on `listing_id`) → run manifest in `data/interim/run_manifests/`. Raw HTML is kept
permanently and independently of the Parquet: when a parser is wrong or markup changes,
**re-parse from disk (`src/parse/reparse_mogi.py`), never re-crawl.**

Scale drives that design. mogi has ~30k phòng-trọ listings in HCMC alone and paginates
past 2,000 pages per province, with **no result count and no last-page link** — an empty
page is the only end-of-slice signal, so totals are unknowable up front and a nationwide
crawl runs for days at the politeness budget (measured ~1,000 listings/h). Hence:
discovery must not block detail fetching, output must be flushed incrementally, and
progress must be checkpointed.

Resumability lives in `data/mogi_seen_urls.db` at two levels: `seen_urls` (listing
fetched|failed) and `frontier` (`last_page_done` per slice, so a resume continues
mid-province rather than re-walking 2,000 pages). A stop part-way through a list page
deliberately leaves that page unmarked so the resume re-walks it. Neither table supports
incremental *re*-crawl for price-change / de-listing tracking yet (Phase 2 backlog).

The four category slugs are **not aliases** — `loi-di-rieng` and `o-chung-chu` share zero
listings with `khu-nha-tro`. Crawl all four and let `listing_id` dedupe the overlap.

`listing_id` is `<source>_<native_id>`, where mogi's native id is the `-id<digits>`
suffix of the detail URL. It is the join/dedupe key throughout.

### alonhadat crawl pipeline

`run_alonhadat.py` is the same orchestrator as `run_mogi.py` — same frontier-of-slices
design, same two-level SQLite resumability, same atomic 200-row Parquet flush, same
clean-Ctrl+C-stop — with a different spider/parser plugged in. Differences worth
knowing before touching either: alonhadat paginates via a URL **path segment**
(`/trang-<n>`) instead of mogi's `?cp=` query param; it has exactly **one** phòng-trọ
category (the `category_paths` list is a one-element list purely so the frontier code
is unchanged); and its province list (34 slugs, the current post-2025-reorg set) came
straight off the site's own province `<select>` dropdown rather than a sitemap harvest.
See `docs/alonhadat_scraping.md` for the full recon and field-mapping writeup —
notably, alonhadat's schema.org-annotated markup gives structured price/area values
directly (no `vn_text.py` regex needed except as a fallback) and exposes **both** the
legacy (pre-reorg) and current (post-reorg) address labels for every listing, which
mogi never does.

The site answers sustained crawling with a CAPTCHA page (HTTP 429, whole IP). `Fetcher`
takes per-site `challenge_markers` from `sources.yaml` and raises `ChallengeEncountered`
on the first response containing one, with no retries. `run_alonhadat.py` then stops the
run and exits 2. Don't turn that into an automatic sleep-and-retry loop: repeatedly
triggering a CAPTCHA and waiting it out is working around the challenge, not slowing
down.

### Phase 3 dedup — deliberate deviations from PLAN.md

`src/clean/dedup.py` departs from PLAN.md's literal recipe in two places; both were found
on real data, and its module docstring explains them. Don't "fix" them back to the plan:
1. **Complete-linkage, not connected components.** Agencies post many *different* rooms
   with template titles at the same price/area, so single-linkage chained unrelated rooms
   into one 37-listing cluster across five HCMC wards.
2. **Address text equality, not lat/lon within 50 m.** Some mogi coordinates are ward
   centroids, so different addresses share identical lat/lon.

Pairwise comparison is exact O(n²) Jaccard, blocked by province. Move to MinHash/LSH if
one province block exceeds ~10–20k rows. Outliers are **flagged** (`is_outlier`,
`outlier_reason`), never dropped.

### batdongsan (prototype, cut) and the "sample" export

`batdongsan` was added outside the mogi/alonhadat architecture and currently violates
project rules. It is also the source PLAN.md marks **cut** (Cloudflare challenge even on
robots.txt) — ask before running or extending it rather than bringing it in line by default:

- **No Parquet path.** `run_batdongsan.py` only saves raw HTML + `data/bds_seen_urls.db`.
  It takes no CLI args: the page cap is hardcoded in `__main__` and the category/province
  are hardcoded in `run()`. It doesn't read policy from `sources.yaml` beyond `base_url`,
  and doesn't use `Fetcher`.
- **Raw PII.** `batdongsan_parser` returns raw `phone` + `poster_name` and never calls
  `pii.py`.
- **Conduct.** `run_batdongsan.py` drives a *headed* Playwright browser
  (`browser_fetcher.py`) with a 15 s pause so a person can clear the Cloudflare
  challenge — that falls under the "no CAPTCHA solving" rule below.
- **`export_mogi_to_sample.py` / `export_batdongsan_to_sample.py`** bypass the Parquet,
  re-read raw HTML, keep Hanoi only, and write a flat 31-column schema to the **repo
  root** (`*_hanoi_extracted.csv`). That schema matches `sample.csv`: 2,108 rows of
  third-party data (PhongTot, Rencity, YourHome) not produced by this repo. The mogi
  exporter regex-extracts the **unmasked phone** from the HTML into
  `contact_phone`/`contact_zalo` — a real violation of the PII rule above, not fixed
  retroactively here. `export_alonhadat_to_sample.py` follows the same 31-column shape
  (see below) but does **not** repeat this: it writes `phone_hash` into those columns,
  since `alonhadat_parser.parse_detail_page()` already returns it hashed.
- **`src/export/text_features.py`** — the keyword-based amenity flags and utility-price
  regexes shared by all three `*_to_sample.py` exporters (this is the "second,
  regex-based amenity extractor that duplicates `src/clean/amenities.py`" — it duplicates
  it once now, not once per exporter). Change a keyword list or utility regex here, not
  in an individual exporter.

## Crawling conduct (non-negotiable)

Politeness is a project constraint, not a tuning knob: 1.5–3.0 s jittered delay, no
concurrency against a single host, honest UA with a contact address, hard robots.txt
compliance. **No proxy rotation, fingerprint spoofing, or CAPTCHA solving.** If a site
puts up a real challenge, the response is to slow down or drop the source — that is why
batdongsan is cut. A per-site delay in `sources.yaml` may be slower than 1.5–3.0 s,
never faster (alonhadat: 20–40 s). If a site serves a challenge page, give it
`challenge_markers` so `Fetcher` halts on the page instead of retrying into it.

Geocoding follows Nominatim's usage policy (https://operations.osmfoundation.org/policies/nominatim/):
at most 1 request/s, single thread, every response cached, identifying User-Agent, no
personal data in queries (`src/geo/address.py` strips house numbers), and "© OpenStreetMap
contributors" credited wherever the coordinates are published. It suits one-off jobs of a
few hundred to a couple of thousand requests. Don't schedule it or scale it up; use another
provider or a self-hosted instance for that.

Known trap, already worked around in `fetcher.py`: `RobotFileParser.read()` fetches with
the bare `Python-urllib` UA, Cloudflare 403s it, and `robotparser` reads a 403 as
"disallow everything". Robots.txt must be fetched with the crawler's real UA and passed
to `.parse()`.

## Data & PII on disk

`data/` is gitignored in full — treat the crawled corpus as reproducible-but-expensive
local state. **Root-level CSVs are not gitignored**, and `sample.csv` and
`mogi_hanoi_extracted.csv` contain raw phone numbers. Never `git add .` / `git add -A` in
this repo, and don't commit those files. Scratch files at the root (`inspect_mogi.py`,
`scratch.html`) are ad-hoc debugging, not pipeline code.

## Testing

- `tests/test_mogi_parser.py` / `tests/test_alonhadat_parser.py` — golden-fixture tests:
  real saved pages in `tests/fixtures/<site>/` in, expected dict out, no network. When
  adding or hardening a source, save one list page and one detail page as fixtures and
  assert the canonical fields the same way. A markup change should break a parser test
  loudly rather than silently corrupt a live crawl. batdongsan has no fixtures or tests yet.
- `tests/test_fetcher.py` — `Fetcher` challenge detection against a monkeypatched
  session. Also checks that alonhadat's configured `challenge_markers` match the saved
  CAPTCHA page and none of the real list/detail fixtures.
- `tests/test_sample_schema.py`, `tests/test_geo_address.py`, `tests/test_nominatim.py` —
  flat-CSV cleaning rules, address parsing and result checks (cases taken from real rows
  and real Nominatim near-misses), and the geocoder's caching, pacing and 429 stop against
  a fake session. No network.
- `tests/test_clean.py` — small synthetic DataFrames. The dedup tests pin the two
  deviations above (address-text requirement, no chaining through a shared neighbor);
  keep them passing if you touch `dedup.py`.
