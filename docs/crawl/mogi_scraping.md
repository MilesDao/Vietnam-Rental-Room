# Scraping mogi.vn

How the mogi.vn scraper in this repo works, why it's built this way, and how
to run it. Scope: the **phòng trọ (rental room)** category only — mogi's
listing inventory is much broader (apartments, houses, land), but per
`docs/PLAN.md` this project targets the phòng trọ segment.

## 1. Recon (do this before writing any code)

Read `robots.txt` and understand the rendering mode *before* deciding how to
crawl. For mogi.vn (checked 2026-09-10):

```
User-agent: *
Allow: /
Disallow: /trang-ca-nhan/
Disallow: /*gclid=
Disallow: /*wbraid=
Disallow: /api/
Disallow: /template/
Disallow: /MarketPrice/
Disallow: /Property/

Sitemap: https://mogi.vn/sitemap/sitemap.xml
Sitemap: https://mogi.vn/sitemap/sitemap-detail.xml
```

Everything this scraper touches (`/thue-phong-tro-khu-nha-tro`, `/<city>/thue-phong-tro-khu-nha-tro`,
and individual listing detail pages) sits outside every `Disallow` rule, so
crawling it is allowed. We never touch `/api/` or `/Property/`.

Pages are **server-rendered** — `curl`-ing a listing page returns the full
card/attribute markup in the initial HTML, no JS execution needed. That rules
out Playwright; plain `requests` + `BeautifulSoup(..., "lxml")` is enough and
is far cheaper/faster/more stable than driving a browser.

**Gotcha found while building this:** Python's `urllib.robotparser.read()`
fetches `robots.txt` with the bare `Python-urllib/x.y` user-agent. Cloudflare
(which fronts mogi.vn) 403s that UA, and `robotparser` silently treats an
HTTP 403 as "disallow everything" — so a naive `RobotFileParser().read()`
makes the crawler refuse to fetch *anything*, including pages robots.txt
actually allows. Fix: fetch `robots.txt` ourselves with the same realistic
browser User-Agent the rest of the crawler uses, then hand the text to
`RobotFileParser.parse()` instead of letting it fetch on its own
(`src/crawl/fetcher.py`).

## 2. URL structure

| Purpose | Pattern |
|---|---|
| Category list page, nationwide | `https://mogi.vn/<category>` |
| Category list page, one province | `https://mogi.vn/<province-slug>/<category>` (e.g. `ha-noi`, `ho-chi-minh`) |
| Category list page, one district | `https://mogi.vn/<province-slug>/<district-slug>/<category>` |
| Pagination | append `?cp=<page>` (15 cards/page) |
| Listing detail | `https://mogi.vn/<district-slug>/<category>/<title-slug>-id<native_id>` |

The trailing `-id<digits>` suffix is the stable native listing id used
everywhere in this codebase as `mogi_<native_id>`.

### Enumerating the country (recon, 2026-09-10)

`robots.txt` publishes a sitemap index (`/sitemap/sitemap.xml`) of 129 children,
127 of which are `sitemap-category-*.xml` holding ~123.6k category URLs. Filtering
those for `phong-tro` yields **6,268 list-page URLs**, which is the authoritative
answer to "where does mogi have rental rooms":

- **32 provinces** carry phòng trọ inventory (not the 2 originally configured).
  Inventory is extremely concentrated — `ho-chi-minh` accounts for 4,364 of the
  6,268 sub-pages, `ha-noi` 990, `da-nang` 283, and the remaining 29 provinces
  share a long tail down to 3.
- **Four phòng trọ sub-category slugs** exist, and they are **not aliases**.
  Measured on `ho-chi-minh` page 1: `thue-phong-tro-loi-di-rieng` and
  `thue-phong-tro-o-chung-chu` share **zero** listing ids with
  `thue-phong-tro-khu-nha-tro`, while `thue-phong-tro-nha-tro` overlaps it 11/15.
  Crawling all four and deduping on `listing_id` is what maximises coverage.
- mogi's canonical HCMC slug is `ho-chi-minh`; the previously configured
  `tp-hcm` also resolves, but the sitemap form is what config now uses.

Two properties of the list pages shape the crawler design:

- **Pagination is deep and real.** `ho-chi-minh` serves genuine, non-repeating,
  newest-first results past `cp=2000` (~30k listings) — verified by checking that
  deep pages return distinct ids, real district slugs, and older native ids.
- **There is no result count and no last-page link.** The pager is a sliding
  window of ±4 pages with only prev/next. So the *only* end-of-slice signal is a
  page that returns zero cards, and total volume cannot be known up front.

District- and ward-level pages exist but are redundant: a province page already
paginates through every district in it, and pagination never caps.

## 3. Architecture

```
config/sources.yaml          per-site config: base URL, the 4 phong-tro
                              category slugs, 32 province slugs (biggest
                              market first), pagination, rate limit, retry, UA
src/crawl/fetcher.py          Fetcher: robots.txt enforcement, jittered delay
                              between requests, exponential backoff on
                              429/5xx, single requests.Session per run
src/crawl/pii.py              salted SHA-256 hashing for phone/poster id —
                              used by every source, not just social (Tier 2)
src/crawl/spiders/mogi.py     iter_list_pages(): lazily yields (page, rows)
                              for one province x category slice until an empty
                              page. discover_detail_rows(): older eager
                              variant that buffers a whole slice first
src/parse/vn_text.py          parse_price_vnd(), parse_area_m2() — small
                              regex parsers for Vietnamese number text
                              ("2 triệu 700 nghìn", "15 m2", "Thỏa thuận")
src/parse/mogi_parser.py      parse_list_page(), parse_detail_page() — pure
                              functions of HTML text, no network calls, so
                              they're unit-testable on saved fixtures
src/crawl/run_mogi.py         CLI orchestrator: walks the province x category
                              frontier, interleaving discovery with detail
                              fetch -> save raw gzip HTML -> parse -> flush to
                              Parquet every 200 rows -> write a run manifest
tests/fixtures/mogi/          two real saved pages (list + detail) used as
                              golden fixtures
tests/test_mogi_parser.py     golden tests against those fixtures
```

Design choices worth calling out:

- **Parsers are pure functions of HTML.** `parse_list_page`/`parse_detail_page`
  take a string and return a dict — no requests inside them. That's what
  makes them unit-testable against a frozen fixture instead of the live site,
  and means a markup change only breaks the parser test, not a live crawl.
- **Raw HTML is always kept** (gzip'd, one file per listing, under
  `data/raw/html/mogi/<date>/`), independent of the parsed Parquet output. If
  the parser has a bug or mogi changes a CSS class, re-parse from disk —
  don't re-crawl.
- **Resumable via SQLite, at two levels.** `seen_urls` records every listing id
  already fetched successfully, so re-running never re-hits a URL it already
  has. `frontier` records `last_page_done` per (province, category) slice, so
  an interrupted nationwide run resumes *mid-province* instead of re-walking
  2,000 list pages to get back to where it was.
- **Discovery is interleaved with detail fetching, not done up front.** The
  eager approach (discover a whole city, then fetch) is unusable at this scale:
  HCMC's 2,000+ list pages would mean ~75 minutes before the first row is
  written. `iter_list_pages()` is a generator so each page's cards are fetched
  as soon as that page is parsed.
- **Parquet is flushed every 200 rows, atomically.** A crawl of the full
  country runs for days; writing only at the end would throw away everything on
  an interrupt. Each flush merges the buffer, writes to `.parquet.tmp`, and
  `os.replace()`s it, so an interrupt mid-write cannot truncate a corpus that
  took hours to collect.
- **Ctrl+C is a clean stop.** The first SIGINT/SIGTERM sets a flag; the crawler
  finishes the listing in flight, flushes the buffer, writes its manifest, and
  exits. A second one aborts immediately. If a stop lands part-way through a
  list page, that page is deliberately *not* marked done, so the resume
  re-walks it and picks up the cards it never reached.
- **Politeness:** 1.5–3.0 s jittered delay between requests, one session
  (no concurrency) against a single host, exponential backoff with jitter on
  429/5xx, a real browser User-Agent, and hard compliance with the
  `Disallow` rules above. No proxy rotation, fingerprint spoofing, or
  CAPTCHA handling — if the site ever puts up a real challenge, the answer is
  to slow down or drop the source, not to evade it (see `docs/PLAN.md`,
  Phase 2 risks).

## 4. Field mapping

Extracted from the detail page's `.main-info` block, the `.info-attrs` table,
the breadcrumb, the embedded Google Maps iframe, and the poster/agent block:

| Canonical field | Source on the page |
|---|---|
| `listing_id` | `mogi_<native_id>` parsed from the URL's `-id<digits>` suffix |
| `title` | `.main-info .title h1` |
| `description` | `.info-content-body` (HTML `<br>` converted to newlines) |
| `price_vnd_month`, `price_is_negotiable` | `.main-info > .price` text, parsed by `parse_price_vnd` |
| `area_m2` | `.info-attrs` row labeled "Diện tích sử dụng" |
| `address_raw` | `.main-info .address` |
| `province`, `district` | breadcrumb items 3 and 4 (`ul.breadcrumb`) |
| `lat`, `lon` | `q=<lat>,<lon>` query param on the embedded Google Maps iframe `data-src` |
| `posted_at` | `.info-attrs` row labeled "Ngày đăng" (`dd/mm/yyyy` -> ISO date) |
| `image_urls`, `n_images` | `data-src` of every `.media-item img` in the gallery |
| `poster_name` | `.agent-info .agent-name a` text |
| `poster_id_hash` | salted hash of the agent's profile URL (`/moi-gioi/...`) |
| `phone_hash`, `phone_prefix` | salted hash / carrier-prefix of the phone number embedded in the page's call button (`PhoneFormat('...')`) — **the raw number is never written to the parsed row** |
| `room_type` | hardcoded `"phong_tro"` — this spider only ever crawls that category |

Not extracted here (left to Phase 3/5 of `docs/PLAN.md`, which operate on the
already-crawled corpus): amenity multi-hot columns, deposit/electricity/water
sub-prices buried in free text, admin-unit crosswalk, duplicate detection.

`geo_confidence` is set to `"geocoded_by_source"` rather than `"exact"` — the
map pin comes from mogi's own address-to-coordinate geocoding, not GPS
metadata, so it shouldn't be trusted as a rooftop-accurate coordinate.

## 5. PII handling

Even though mogi is a public classifieds site (Tier 1, not the personal-data
Tier 2 social sources), the canonical schema never stores a raw phone number
or poster identity (`docs/PLAN.md` canonical schema, and `docs/PLAN.md` 2B.2
principle applied uniformly). `src/crawl/pii.py` hashes both with
`sha256(value + PROJECT_SALT)`, truncated to 16 hex chars; only a 4-digit
carrier `phone_prefix` survives in the clear. Set `PROJECT_SALT` in the
environment before crawling for real (it defaults to a dev value otherwise).

Note the raw phone number the poster typed into their own ad text (e.g. "LH:
0912xxxxxx") still appears inside `description` — that's the ad copy as
authored and publicly published by the poster, not a value this crawler
derives or stores separately.

## 6. Running it

```bash
pip install -r requirements.txt

# Small smoke run: 5 new detail pages from one province + one sub-category
python -m src.crawl.run_mogi --city hanoi --max-pages 1 --max-details 5 \
    --categories thue-phong-tro-khu-nha-tro

# Everything mogi has in Vietnam: 32 provinces x 4 sub-categories, each slice
# walked until it runs out of pages. Resumable -- Ctrl+C and re-run to continue.
python -m src.crawl.run_mogi --city all --categories all

# Specific provinces (CLI aliases hanoi/hcmc, or raw mogi slugs)
python -m src.crawl.run_mogi --city hcmc,da-nang,binh-duong

# Unit tests (run against saved fixtures, no network needed)
python -m pytest tests/test_mogi_parser.py -v
```

Expect the nationwide crawl to take **days**, not hours. Measured throughput at
the configured 1.5–3.0 s delay is **~1,000 listings/hour** (one list page plus
its 15 detail pages costs ~55 s), and HCMC alone is ~30k listings per
sub-category. That is a deliberate trade: the politeness budget is a
project constraint (§3), so the crawl is built to be stopped and resumed rather
than to finish in one sitting. Watch it with:

```bash
tail -f "$(cat data/logs/CURRENT)"
```

Outputs:

- `data/raw/html/mogi/<date>/<listing_id>.html.gz` — raw HTML, kept forever
- `data/interim/parsed_mogi.parquet` — canonical rows, deduped on `listing_id`
  and appended to on every run
- `data/interim/run_manifests/mogi_<run_id>.json` — per-run counts
  (`n_fetched`, `n_failed`, `n_skipped_already_seen`)
- `data/mogi_seen_urls.db` — resumability state (`seen_urls` + `frontier`)
- `data/logs/crawl_mogi_<ts>.log` — crawl log; `data/logs/CURRENT` names the latest

Rebuild the Parquet from retained raw HTML at any time:

```bash
python -m src.parse.reparse_mogi --dry-run   # report
python -m src.parse.reparse_mogi             # rebuild in place
```

Needed after a parser fix, after rotating `PROJECT_SALT`, or after a *hard*
kill: rows buffer until the 200-row flush, and `seen_urls` marks a listing
fetched as soon as its HTML is on disk, so a `kill -9` can leave up to 200
listings recorded-and-saved but absent from the Parquet. Ctrl+C does not have
this problem — it flushes on the way out.

## 7. Known limitations / not yet built

- **Images are not downloaded**, only their URLs are captured. Phase 2's
  "Stage C" image-fetch/resize/hash pipeline (`docs/PLAN.md`) isn't wired up
  for mogi yet.
- The Vietnamese price/area parsers (`src/parse/vn_text.py`) cover the common
  patterns seen in this category (`"X triệu"`, `"X triệu Y nghìn"`, `"XtrY"`
  shorthand, `"Thỏa thuận"`) but are heuristic, not exhaustive — Phase 3's
  hardened parser should absorb and extend these rather than trust them
  blindly on the full corpus.
- Only the phòng trọ categories are crawled. Extending to mogi's other rental
  categories means adding slugs to `category_paths` in `config/sources.yaml`,
  not new code.
- **Coverage is bounded by what mogi's province pages paginate to.** A listing
  that exists on the site but is not reachable by walking a province x category
  list page will not be found. The ward/street/project-level pages in the
  sitemap (6,005 of the 6,268 harvested URLs) are unused because province pages
  already cover their districts; if a province ever turns out to cap its
  pagination, those finer slices are the fallback.
- Province slugs are frozen from the 2026-09-10 sitemap harvest. mogi adding a
  province later will not be picked up until that list is refreshed — re-run
  the sitemap harvest to check.
- **The 2025 provincial reorganisation is not reconciled here.** mogi still uses
  legacy province/district labels, which is what lands in `province`/`district`.
  Mapping to current admin codes is Phase 3's crosswalk job (`docs/PLAN.md`),
  deliberately not done at crawl time.
- No incremental re-crawl of already-seen listings (for price-change /
  de-listing tracking) yet — the `seen_urls` table only records "fetched
  once", per Phase 2's weekly re-crawl idea.
