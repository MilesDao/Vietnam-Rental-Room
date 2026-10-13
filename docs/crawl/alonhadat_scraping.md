# Scraping alonhadat.com.vn

How the alonhadat.com.vn scraper in this repo works, why it's built this way,
and how to run it. Scope: the **phòng trọ (rental room)** category only, same
as mogi — see `docs/mogi_scraping.md`, which this scraper's architecture
mirrors throughout. Per `docs/PLAN.md` recon, alonhadat is Tier-1 priority #3
("no bot protection at all"), behind Chotot and phongtro123 (neither has code
yet) and ahead of mogi. That recon note no longer holds: under sustained
crawling the site serves a CAPTCHA page. Read §8 before running anything
longer than a smoke test.

This replaces `docs/alonhadat_crawling_methodology.md`, which documented a
prior implementation (BrowserFetcher/Playwright, old-style `.html` URLs) that
no longer matches either the site or the code.

## 1. Recon (do this before writing any code)

Checked live 2026-09-11:

```
User-agent: *
Disallow: /publish/handler/*
Disallow: /publish/form/*
Disallow: /can-mua*
Disallow: /can-thue*
Disallow: /nha-dat/can-mua*
Disallow: /nha-dat/can-thue*

Sitemap: https://alonhadat.com.vn/sitemap.xml
```

Everything this scraper touches (`/cho-thue-phong-tro-nha-tro/...` list pages,
`*-<id>.html` detail pages) sits outside every `Disallow` rule.

Pages are **server-rendered** — plain `requests` + `BeautifulSoup(..., "lxml")`
returns the full listing markup, no JS execution needed. That rules out
Playwright, which the *previous* implementation used unconditionally (see
"What changed" below) — it was never actually required by this site.

Unlike mogi, alonhadat's `robots.txt` is **not** behind Cloudflare and does not
403 the bare `Python-urllib` user-agent, so the "fetch robots.txt with a real
UA" workaround in `src/crawl/fetcher.py` isn't load-bearing here — it's applied
anyway because `Fetcher` is shared code, and it's harmless.

## 2. URL structure

The site redesigned its URLs at some point after `docs/alonhadat_crawling_methodology.md`
was written; the old `/nha-dat/cho-thue/phong-tro-nha-tro/1/<city>.html` form
now 301-redirects to the current scheme below. Always follow a redirect during
recon rather than trusting a URL pattern found in old docs or old code.

| Purpose | Pattern |
|---|---|
| Category list page, one province, page 1 | `https://alonhadat.com.vn/cho-thue-phong-tro-nha-tro/<province-slug>` |
| Category list page, page N > 1 | same, with `/trang-<N>` appended |
| Category list page, nationwide | `https://alonhadat.com.vn/cho-thue-phong-tro-nha-tro` |
| Listing detail | `https://alonhadat.com.vn/<title-slug>-<native_id>.html` |

Pagination is a **path segment**, not mogi's `?cp=` query param — confirmed
from the list page's own `<link rel='next' href='.../trang-2'>`. The detail
URL's trailing `-<digits>.html` is the stable native id, used everywhere in
this codebase as `alonhadat_<native_id>` (the earlier implementation used an
`alo_` prefix; this scraper switched to the full source name to match the
`<source>_<native_id>` convention documented in `CLAUDE.md`).

There is exactly **one** phòng trọ category on alonhadat (no
`khu-nha-tro`/`nha-tro`/etc split like mogi's four sub-categories).
`config/sources.yaml`'s `category_paths` is still a one-element list, purely
so `run_alonhadat.py` can reuse `run_mogi.py`'s province-x-category frontier
code unchanged.

### Enumerating the country (recon, 2026-09-11)

Unlike mogi (which needed a sitemap harvest to find its province list), every
alonhadat page ships a `<select id="...slProvince">` search-form dropdown
whose `data-newlink` attribute on each `<option>` **is** the current URL slug
— already deduplicated, since several pre-2025-reorg provinces collapse to
one post-reorg slug (e.g. the dropdown lists Hà Nam and Nam Định as separate
options, both carrying `data-newlink="ninh-binh"`). Reading that one dropdown
off any page gives the authoritative province list directly — **34 slugs**,
matching Vietnam's 2025 administrative reorganization (63 → 34 provinces).

Two properties shape the crawler design, both smaller-scale than mogi:

- **Inventory is small.** The nationwide list page reports **1,878** phòng
  trọ listings total; Hanoi alone accounts for **1,410** of them (~75%). mogi
  has ~30k listings in HCMC *alone*. By size alone a nationwide alonhadat
  crawl would be a same-day job; the CAPTCHA (§8) is what actually limits it.
- **Same end-of-slice signal as mogi: no result count exposed per page, and
  no last-page link** (the "Tìm thấy N tin" count is nationwide/per-province
  total, not remaining-pages). 20 cards/page, verified no id overlap between
  consecutive pages and an empty page at `trang-500` on a ~71-page province.
  So `iter_list_pages()` again terminates on the first zero-card page.

## 3. Architecture

```
config/sources.yaml              per-site config: base URL, the one phong-tro
                                  category path, 34 province slugs, path-segment
                                  pagination, rate limit, retry, UA, and the
                                  CAPTCHA page's challenge_markers
src/crawl/fetcher.py             Fetcher -- shared with mogi; raises
                                  ChallengeEncountered, with no retries, on any
                                  response containing a challenge marker
src/crawl/pii.py                 salted SHA-256 hashing -- shared with mogi, unchanged
src/crawl/spiders/alonhadat.py   iter_list_pages(): lazily yields (page, rows)
                                  for one province slice until an empty page --
                                  same generator shape as spiders/mogi.py, but
                                  a path-segment URL builder instead of ?cp=
src/parse/vn_text.py             parse_price_vnd()/parse_area_m2() -- used only
                                  as a fallback here (see field mapping below)
src/parse/alonhadat_parser.py    parse_list_page(), parse_detail_page() -- pure
                                  functions of HTML text, no network calls
src/crawl/run_alonhadat.py       CLI orchestrator -- structurally identical to
                                  run_mogi.py: province x category frontier,
                                  raw gzip HTML, flush to Parquet every 200
                                  rows, run manifest, resumable SQLite state
src/parse/reparse_alonhadat.py   rebuild the Parquet from retained raw HTML
tests/fixtures/alonhadat/        one real list page + one real detail page
                                  (Hà Đông, Hà Nội) + the real CAPTCHA page,
                                  all saved 2026-09-11
tests/test_alonhadat_parser.py   golden tests against the list/detail fixtures
tests/test_fetcher.py            challenge detection, offline; also checks the
                                  configured markers hit the CAPTCHA fixture
                                  and miss the real pages
```

Every design choice in `docs/mogi_scraping.md` §3 (pure-function parsers, raw
HTML kept forever, two-level SQLite resumability, interleaved discovery,
atomic 200-row Parquet flush, clean-stop on Ctrl+C) applies here unchanged —
this is the same orchestrator with a different spider and parser plugged in.
Two things differ: the per-request delay is much longer, and a CAPTCHA page
stops the run outright (§8). Other differences are called out below.

### What changed from the previous implementation

The code this replaced (`src/crawl/run_alonhadat.py` + `spiders/alonhadat.py`
+ `parse/alonhadat_parser.py`, as of the initial `PLAN` commit) diverged from
every one of those conventions, and from the project's non-negotiable
crawling-conduct rules:

- No `Fetcher` — a bare `requests.Session` with a hardcoded 4-retry loop
  inlined into the spider, and a second, dead code path (`iter_list_pages`)
  that drove `BrowserFetcher` (Playwright) for a site that doesn't need it.
- **No robots.txt check at all.**
- Raw `phone`/`poster_name` in the parsed dict — never hashed via `pii.py`,
  in violation of the rule in `CLAUDE.md` that applies to *every* source.
- No Parquet output, no resumability `frontier` table, no run manifest, no
  CLI flags — `run()` took no arguments; the page cap and category were
  hardcoded in `__main__`.
- Scraped the stale pre-redesign URL scheme (silently 301-redirected by the
  site, which happened to still work, but meant the list-page parser's
  selectors — `div.content-item a` / `div.vip a` / `div.normal a` — no longer
  matched anything on the page actually returned).

None of that is preserved. `docs/alonhadat_crawling_methodology.md` described
that implementation and is now superseded by this file.

## 4. Field mapping

alonhadat's detail page is schema.org-annotated (`itemscope`/`itemprop`
microdata for `RealEstateListing`/`Offer`/`PostalAddress`), which gives
structured price/area/address values directly — mogi's HTML has none of that,
which is why `vn_text.py`'s regex parsers matter more there. Here they're
used only as a fallback for whatever a future listing doesn't structure as
microdata (e.g. a genuinely negotiable price with no `price` itemprop).

| Canonical field | Source on the page |
|---|---|
| `listing_id` | `alonhadat_<native_id>` parsed from the URL's `-<digits>.html` suffix |
| `title` | `article.property [itemprop='name']` |
| `description` | `article.property [itemprop='description']` |
| `price_vnd_month`, `price_is_negotiable` | `data[itemprop='price']`'s `value` attribute (already a plain VND integer, no text parsing needed); falls back to `parse_price_vnd` on the display text if absent |
| `area_m2` | `[itemprop='floorSize'] [itemprop='value']` (already a plain number) |
| `posted_at` | `[itemprop='datePosted']`'s `datetime` attribute (already ISO `YYYY-MM-DD` — no `dd/mm/yyyy` parsing needed, unlike mogi) |
| `province`, `district`, `ward`, `address_raw` | `p.old-address` — see below |
| `admin_new_province`, `admin_new_ward` | `[itemprop='address'] [itemprop='addressRegion' / 'addressLocality']` — see below |
| `image_urls`, `n_images` | `src` of every `section.images ul.image-list img` |
| `poster_name` | `aside.right section.contact .name` |
| `poster_id_hash` | salted hash of the numeric member id (`#hddNguoiDang` hidden input) |
| `phone_hash`, `phone_prefix` | salted hash / carrier-prefix of the digits in `aside.right section.contact .fone a`'s `tel:` href — **the raw number is never written to the parsed row** |
| `legal_status` | the "Pháp lý" row of the `section.moreinfor1` details table, `---`/`_` placeholders normalized to `None` |
| `lat`, `lon`, `geo_confidence` | always `None` — see "No coordinates" below |
| `room_type` | hardcoded `"phong_tro"`, same as mogi |

### Two addresses, on purpose

Every listing's address is rendered **twice** on the page, and this parser
keeps both, because they answer different questions `docs/PLAN.md`'s Phase 3
crosswalk cares about:

- **`p.old-address`** — the pre-2025-reorg label (`", <ward>, <district>,
  <province>"`, comma-separated, oldest units first) — `province`/`district`/
  `ward`/`address_raw` are parsed from this, matching mogi's semantics exactly
  (mogi's breadcrumb only ever gives you this legacy scheme too; see
  `docs/mogi_scraping.md` §7).
- **`[itemprop='address']`** — the *current* (post-reorg) `addressRegion` /
  `addressLocality`, straight from the page's own schema.org markup — kept as
  `admin_new_province` / `admin_new_ward`.

This is a genuine advantage over mogi: `docs/PLAN.md` Phase 3 calls for a
legacy-label-to-new-admin-code crosswalk sourced externally, and alonhadat's
own markup already hands you both ends of that mapping for every listing it
carries, no external crosswalk table needed for this source. mogi never
surfaces the new-scheme labels at all.

The `(cũ)` / `(địa chỉ cũ)` marker the site renders next to the old address is
stripped in `_parse_old_address` — it lands inside the scraped tag on some
pages and just outside it on others, a markup inconsistency on the site's
side, not a parsing choice.

### No coordinates

alonhadat detail pages ship a `ViewPropertyInFrame(lat, lng)` JS helper that
*can* render a Google Maps iframe, but no call site with real coordinates was
found on any recon page — the poster evidently has to opt in to pinning a
location, and none of the sampled listings had. `lat`/`lon`/`geo_confidence`
are therefore always `None` for this source (contrast mogi, whose map iframe
`data-src` is present on essentially every listing). Phase 4 geocoding will
need to run an actual address→coordinate geocoder against alonhadat's
`address_raw`/`admin_new_*` fields; there is no source-provided pin to trust
here the way there is for mogi.

## 5. PII handling

Same principle and same module as mogi (`docs/mogi_scraping.md` §5):
`src/crawl/pii.py` hashes phone and poster id with `sha256(value +
PROJECT_SALT)`, truncated to 16 hex chars; only a 4-digit carrier
`phone_prefix` survives in the clear, and the canonical row never stores a
raw phone number or poster identity.

One implementation nuance worth calling out: alonhadat renders the phone
number with punctuation (`0968.688.968`), whereas mogi's regex already
captures pure digits. The parser normalizes to digits-only (`re.sub(r"\D",
"", ...)`) **before** hashing, not after — hashing the punctuated string
would make the same real phone number hash differently depending on which
site posted it, breaking `phone_hash` as a cross-source dedupe key (`docs/PLAN.md`
Phase 3, layer 5). This matters more here than it would for a single-source
corpus.

Also note, as with mogi: the raw phone number the poster typed into their own
ad text (e.g. "📞 Liên hệ chính chủ: 0968.688.968") still appears inside
`description` — that's the ad copy as authored and publicly published by the
poster, not a value this crawler derives or stores separately.

## 6. Running it

```bash
pip install -r requirements.txt

# Small smoke run: 5 new detail pages from Hanoi
python -m src.crawl.run_alonhadat --city hanoi --max-pages 1 --max-details 5

# Everything alonhadat has in Vietnam: 34 provinces, walked to the end of
# each. Resumable -- Ctrl+C and re-run to continue.
python -m src.crawl.run_alonhadat --city all

# Specific provinces (CLI aliases hanoi/hcmc, or raw alonhadat slugs)
python -m src.crawl.run_alonhadat --city hcmc,da-nang

# Unit tests (run against saved fixtures, no network needed)
python -m pytest tests/test_alonhadat_parser.py -v
```

Verified live (2026-09-11): a `--city hanoi --max-pages 1 --max-details 5`
smoke run fetched 5/5 listings with 0 failures in ~22 s at the then-configured
1.5–3.0 s delay. Re-running it immediately skipped all 5 already-`fetched`
ids and pulled the next 5 new ones from the same page.

Two unbounded `--city hanoi` runs the same day both ran into the site's
CAPTCHA page (§8) and were stopped by hand:

| Run | Delay | Requests before the CAPTCHA | Listings fetched |
|---|---|---|---|
| 1 (~19:03) | 1.5–3.0 s | ~30, in ~1.5 min | 29 |
| 2 (~21:56, ~3 h after run 1) | 3.0–5.0 s | ~45, in ~3 min | 40 more (69 total) |

At the time the crawler didn't recognise the page. It treated each challenge
response as an ordinary 429, spent 4 retries on it, then moved on to the next
listing. It now stops at the first one (§8). The page body was only inspected
on a later probe, but every failure in both runs was the same 429.

An earlier version of this section described the block as a session-cookie
rate limit that cleared after ~20 minutes. Both claims were wrong. A
cookie-less `curl` got the same page, so the block covers the whole IP. The
gap between the two runs was ~3 hours, not 20 minutes. And the page was still
being served 32 minutes after run 2's last request.

The configured delay is now 20–40 s. That is a guess, ~8x slower than the pace
that triggered the CAPTCHA, not a rate measured to stay under it. At that pace
the ~1,400 Hanoi requests would take ~12 hours.

Outputs (same layout as mogi, `<site>` = `alonhadat`):

- `data/raw/html/alonhadat/<date>/<listing_id>.html.gz` — raw HTML, kept forever
- `data/interim/parsed_alonhadat.parquet` — canonical rows, deduped on `listing_id`
- `data/interim/run_manifests/alonhadat_<run_id>.json` — per-run counts
- `data/alonhadat_seen_urls.db` — resumability state (`seen_urls` + `frontier`)

Rebuild the Parquet from retained raw HTML at any time:

```bash
python -m src.parse.reparse_alonhadat --dry-run   # report
python -m src.parse.reparse_alonhadat             # rebuild in place
```

## 7. Sample CSV export

`src/export/export_alonhadat_to_sample.py` re-reads the raw gzip HTML directly
(bypassing the Parquet) and writes a flat, human-browsable
`alonhadat_hanoi_extracted.csv` at the repo root — same 31-column shape as
`export_mogi_to_sample.py`'s `mogi_hanoi_extracted.csv` (title, district,
ward, address, price, area, five utility-price snippets, eight amenity
booleans plus an `amenities_list` summary, image count/urls, contact fields,
listing url), Hanoi-only, one row per raw HTML file on disk:

```bash
python -m src.export.export_alonhadat_to_sample
```

The keyword-based amenity/utility-price extraction (a second, cruder pass
than `src/clean/amenities.py`'s negation-aware lexicon — see that module's
docstring) now lives once, in `src/export/text_features.py`, shared by both
this exporter and `export_mogi_to_sample.py`, rather than copy-pasted per
source.

**One deliberate difference from the mogi version:** `contact_phone` /
`contact_zalo` hold `phone_hash` (already computed by
`alonhadat_parser.parse_detail_page`), not a raw phone number.
`export_mogi_to_sample.py` writes the unmasked number into those columns,
which is a real violation of this project's own PII rule — see
`CLAUDE.md`'s "batdongsan (prototype, cut) and the 'sample' export" section —
but that file's behavior wasn't in scope to change here, and it is not
repeated for a second source.

## 8. Known limitations / not yet built

- **Sustained crawling gets a CAPTCHA, so PLAN.md's "no bot protection at
  all" recon note is out of date.** After a few dozen requests the site stops
  serving pages. Instead it returns a "Vui lòng xác minh không phải Robot"
  page with HTTP 429, asking for the names of three animals shown in an image.
  The page says the site "bị kẻ xấu dùng phần mềm để phá hoại" (is being
  attacked by people using software). It is served to the whole IP: a
  cookie-less `curl` from the same machine gets it too. §6 lists the two runs
  that triggered it.

  What the code does about it:
  - `Fetcher` raises `ChallengeEncountered` on any response whose body or final
    URL contains one of `config/sources.yaml`'s `alonhadat.challenge_markers`.
    It does this whatever the status code, and never retries.
  - `run_alonhadat.py` then stops the whole run. The listing it was fetching
    gets no `seen_urls` row, so a later run picks it up, and the same goes for
    the page it was on. The manifest records `stopped_by_challenge: true` and
    the process exits with status 2.
  - Detection sits in `Fetcher`, not the parser, because of challenges served
    with HTTP 200. The parser would read one as an empty list page, i.e. "slice
    exhausted", or as a detail row with every field missing.

  What it deliberately does not do, per `CLAUDE.md`'s crawling-conduct rules:
  solve the CAPTCHA, have a person solve it and reuse their session (the
  batdongsan prototype's approach), sleep through the block and resume
  automatically, or change IP. PLAN.md cut batdongsan for serving a challenge.
  It is an open project decision whether alonhadat stays in at a much slower
  pace (20–40 s configured; §6) or is cut the same way. If a slow run hits the
  CAPTCHA too, treat that as the answer. None of the 69 raw pages saved before
  this fix contain a challenge marker, so the existing corpus is clean.

- **No source-provided coordinates** (§4) — Phase 4 geocoding is mandatory
  for this source, not optional the way it might be for mogi.
- **Images are not downloaded**, only their URLs are captured — same gap as
  mogi; Phase 2's Stage C image pipeline isn't wired up for either source yet.
- Province slugs are read off the site's own dropdown as of 2026-09-11; if
  alonhadat ever changes its provincial coverage, re-scrape that `<select>`
  rather than trusting this frozen list indefinitely (same caveat as mogi's
  frozen sitemap harvest).
- `run_clean.py` (Phase 3) only reads mogi's Parquet today
  (`docs/PLAN.md`/`reports/cleaning_report.md` says "Tier 1 only -- mogi.vn").
  Once this crawler has real output, `load_interim()`'s `parsed_*.parquet`
  glob will pick alonhadat rows up automatically, but the cleaning report's
  text and the dedupe/outlier thresholds have only been sanity-checked
  against mogi's data shape — re-verify against a real alonhadat run before
  trusting the merged output.
- No incremental re-crawl of already-seen listings (price-change /
  de-listing tracking) — same backlog item as mogi.
