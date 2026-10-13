# Fresh Re-crawl With Working Links and Images — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-crawl the newest Hanoi rental listings from every source except Facebook, such that each row has a `listing_url` that opens that exact ad and `image_urls` that actually load.

**Architecture:** Keep each source's existing crawler. Add one shared contract (`src/clean/link_check.py`: per-platform URL shape + canonical image list) that every source's output must pass, a live sampling checker (`src/crawl/verify_sample.py`) that proves links/images work, and gate `prepare.py` so bad links are blanked instead of shown.

**Tech Stack:** Python 3.12, requests, pandas, pytest. Existing `Fetcher` (robots, delays, `ChallengeEncountered`).

**Spec:** user request 2026-10-06 + findings in this session (below). No separate spec doc.

## Findings that drive the plan (measured on `data/unified_hanoi_rentals_dedup.csv`, 15,745 rows)

- Only phongtro123 rows carry a post date (30%); median age ~850 days, oldest 2020 → data is stale.
- `listing_url` is wrong/unusable for: **YourHome** (all `https://yourhome.top/?city=ha-noi`, no per-room permalink), **Rencity** (`rencity.vn/search?post_id=N`, a search page, untested), **Mogi** (`src/export/export_mogi_to_sample.py:51` *fabricates* `https://mogi.vn/dummy-id<N>` from the raw filename instead of using the real URL), **Facebook** (out of scope).
- Image formats are inconsistent: `" | "`-joined string (alonhadat, mogi, rencity, yourhome), JSON list (phongtro123), Python-repr list (chotot), `[]` (facebook).
- phongtro123 parser (`crawlers/phongtro123/src/parse/phongtro123_parser.py:172-180`) takes the first 8 `<img>` on the page; sampled rows mix 900x600 gallery images with 450x300 thumbs from different dates → likely images of *other* "related" listings.
- alonhadat serves a CAPTCHA after ~30–45 requests; `config/sources.yaml` sets 20–40 s delays (~12 h for Hanoi). A challenge is a hard stop, never retried or bypassed.
- Hotlinking: image CDNs may reject requests with a foreign `Referer`; the app loads them from the browser, so the checker must test without a Referer.

## Global Constraints

- **Hanoi only** for every source (filter at crawl time where the site/API allows, and again in `prepare.py` on `city`). Facebook is excluded; keep its existing rows untouched.
- Source sites (given by the user 2026-10-06): https://yourhome.top/ , https://www.nhatot.com/ (Chotot's current domain; `nha.chotot.com` now redirects to `www.nhatot.com/thue-phong-tro/<ad_id>`), https://rencity.vn/ .
- Obey robots.txt; any `ChallengeEncountered` ends that source's run (resume later from the SQLite checkpoint). No CAPTCHA solving, no proxies.
- Hash phones/poster identity at ingest (`src/crawl/pii.py`); never output raw phone/name. Don't rotate `.project_salt`.
- `data/` is gitignored local state: write new outputs to new, dated files (`data/interim/recrawl_2026-10/`), never overwrite existing CSVs.
- Nominatim ≤ 1 req/s, cached.

## Review Focus

- A link that returns HTTP 200 but is an expired/"tin đã hết hạn" page or a redirect to a category/home page → must count as failed, not passed.
- A list of images where all entries belong to *other* listings (related-ads widget) → must fail the image check (tested via host/size pattern + per-listing uniqueness).
- Image string in any of the 3 legacy formats (`a | b`, JSON list, Python repr) → `parse_images` returns the same clean list.
- Same URL used by two different listings (YourHome-style home link) → flagged as non-permalink.
- Listing with zero valid images → kept, `image_urls` empty list, app shows placeholder (do not drop the room).

---

### Task 1: URL + image contract

**Files:**
- Create: `src/clean/link_check.py`
- Test: `tests/test_link_check.py`

**Interfaces:**
- Produces: `is_permalink(platform: str, url: str | None) -> bool`; `parse_images(value) -> list[str]` (accepts list, JSON str, Python-repr str, `" | "`-joined str, NaN/None); `mark_bad_links(df) -> pd.Series[bool]` (True where `listing_url` is not a permalink OR is duplicated within its platform).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_link_check.py
import pandas as pd
from src.clean.link_check import is_permalink, parse_images, mark_bad_links

def test_permalinks():
    assert is_permalink("Mogi.vn", "https://mogi.vn/ha-noi/thue-phong-tro/phong-tro-cau-giay-id22046391")
    assert not is_permalink("Mogi.vn", "https://mogi.vn/dummy-id22046391")
    assert is_permalink("ChoTot.com", "https://nha.chotot.com/thue-phong-tro/134126101")
    assert is_permalink("Alonhadat.vn", "https://alonhadat.com.vn/phong-dep-19042998.html")
    assert is_permalink("Phongtro123.com", "https://phongtro123.com/phong-tro-x-pr588674.html")
    assert is_permalink("YourHome.top", "https://yourhome.top/room/1791207671066")
    assert not is_permalink("YourHome.top", "https://yourhome.top/?city=ha-noi")
    assert is_permalink("Rencity.vn", "https://rencity.vn/post/phong-501-32917")
    assert not is_permalink("Rencity.vn", "https://rencity.vn/search?post_id=1")
    assert not is_permalink("Mogi.vn", None)

def test_parse_images_all_formats():
    want = ["https://a/1.jpg", "https://a/2.jpg"]
    assert parse_images("https://a/1.jpg | https://a/2.jpg") == want
    assert parse_images('["https://a/1.jpg", "https://a/2.jpg"]') == want
    assert parse_images("['https://a/1.jpg', 'https://a/2.jpg']") == want
    assert parse_images(want) == want
    assert parse_images(float("nan")) == [] and parse_images("[]") == []

def test_mark_bad_links_flags_duplicates():
    df = pd.DataFrame({"platform": ["X", "X", "Y"], "listing_url": ["u", "u", "u"]})
    assert mark_bad_links(df, check_shape=False).tolist() == [True, True, False]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_link_check.py -q` → Expected: FAIL (ImportError).

- [ ] **Step 3: Write minimal implementation**

```python
# src/clean/link_check.py
"""Contract every source must meet: a per-listing permalink and a clean image list."""
import ast
import json
import re

import pandas as pd

# A permalink = the URL shape that identifies ONE ad on that site.
PERMALINK = {
    "Mogi.vn": r"^https://mogi\.vn/(?!dummy-id).+-id\d+/?$",
    "Alonhadat.vn": r"^https://alonhadat\.com\.vn/.+-\d+\.html$",
    "Phongtro123.com": r"^https://phongtro123\.com/.+-pr\d+\.html$",
    "ChoTot.com": r"^https://(www\.nhatot\.com|nha\.chotot\.com)/.+/\d+$",   # old links redirect to nhatot.com
    "Facebook": r"^https://www\.facebook\.com/groups/\d+/posts/\d+",
    "Rencity.vn": r"^https://rencity\.vn/post/.+-\d+$",     # verified 2026-10-06 (Task 6)
    "YourHome.top": r"^https://yourhome\.top/room/\d+$",     # verified 2026-10-06 (Task 6)
}


def is_permalink(platform, url):
    pat = PERMALINK.get(platform)
    return bool(pat and isinstance(url, str) and re.match(pat, url))


def parse_images(value):
    if isinstance(value, list):
        return [str(x) for x in value]
    if not isinstance(value, str) or not value.strip():
        return []
    s = value.strip()
    if s.startswith("["):
        for loader in (json.loads, ast.literal_eval):
            try:
                return [str(x) for x in loader(s)]
            except (ValueError, SyntaxError):
                pass
        return []
    return [p.strip() for p in s.split("|") if p.strip().startswith("http")]


def mark_bad_links(df, check_shape=True):
    """True where listing_url is not a permalink or is shared by several rows of the same platform."""
    dup = df.duplicated(["platform", "listing_url"], keep=False)
    if not check_shape:
        return dup
    shape = pd.Series([is_permalink(p, u) for p, u in zip(df.platform, df.listing_url)], index=df.index)
    return dup | ~shape
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_link_check.py -q` → Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/clean/link_check.py tests/test_link_check.py
git commit -m "feat: per-platform listing permalink + image list contract"
```

---

### Task 2: Live sample verifier (the acceptance gate)

**Files:**
- Create: `src/crawl/verify_sample.py`
- Test: `tests/test_verify_sample.py` (pure-function part only; network part is run manually)

**Interfaces:**
- Consumes: `is_permalink`, `parse_images` from Task 1.
- Produces: `python -m src.crawl.verify_sample <csv> [--n 25]` prints per-platform pass rate for (a) link opens with 200, final URL still contains the listing id, body has no expiry marker; (b) first image returns `image/*` with **no Referer** header. Exit code 1 if any platform < 95%. `looks_expired(html: str) -> bool` is unit-tested.

- [ ] **Step 1: Failing test**

```python
# tests/test_verify_sample.py
from src.crawl.verify_sample import looks_expired

def test_expired_markers():
    assert looks_expired("<h1>Tin đăng đã hết hạn</h1>")
    assert looks_expired("Không tìm thấy trang")
    assert not looks_expired("<h1>Phòng trọ Cầu Giấy 3tr</h1>")
```

- [ ] **Step 2:** Run `python -m pytest tests/test_verify_sample.py -q` → FAIL (ImportError).

- [ ] **Step 3: Implement** `looks_expired` (case-insensitive substring match on `hết hạn`, `đã bán`, `đã cho thuê`, `không tìm thấy`, `404`, `tin không tồn tại`) and `main()`: load CSV, `groupby("platform").sample(min(n, len))`, for each sampled row use `requests.get(url, timeout=20, allow_redirects=True, headers={"User-Agent": <config user_agent>})` with a 2 s sleep between hosts' requests; link passes if `status==200`, `looks_expired(text)` false and the listing's native id (digits at end of URL or `listing_id`) appears in `resp.url`; image passes if `requests.get(first_image, timeout=20, stream=True)` is 200 with `content-type` starting `image/` and no `Referer` sent. Print table `platform | n | link_ok% | image_ok%`; `sys.exit(1)` if any `< 95`. Skip Facebook.

- [ ] **Step 4:** Run the unit test → PASS. Smoke the CLI on the *current* file to capture the baseline: `python -m src.crawl.verify_sample data/unified_hanoi_rentals_dedup.csv --n 10` and save output to `data/interim/recrawl_2026-10/baseline.txt`. Expected: YourHome/Rencity/Mogi fail (this proves the checker works).

- [ ] **Step 5: Commit** `git add src/crawl/verify_sample.py tests/test_verify_sample.py && git commit -m "feat: live link/image sample verifier"`

---

### Task 3: Mogi — real URLs and fresh crawl

**Files:**
- Modify: `src/export/export_mogi_to_sample.py:51` (stop fabricating `dummy-id` URLs)
- Run: `src/crawl/run_mogi.py`

- [ ] **Step 1: Find where the real URL is kept.** Read `src/crawl/run_mogi.py` (how raw HTML is saved and what the parquet row's `url` holds) and `src/export/export_mogi_to_sample.py:40-60`. Decision rule: if parsed parquet rows (`data/interim/`) contain the real `url`, make the exporter read it from there; otherwise save the URL next to the raw file (sidecar `.url` or inside run_mogi's row flush) and read it back.
- [ ] **Step 2: Failing test** in `tests/test_sample_schema.py` (or new `tests/test_export_mogi.py`): export from a fixture whose real URL is `https://mogi.vn/ha-noi/.../x-id123`; assert `listing_url` equals it and `is_permalink("Mogi.vn", url)`.
- [ ] **Step 3:** Implement the fix per Step 1's rule; run the test → PASS.
- [ ] **Step 4: Fresh crawl** (resumable; Ctrl+C safe): `python -m src.crawl.run_mogi --city hanoi --categories all --max-pages 200` then check `listing_id`s newer than the existing set. Each category ordering is newest-first, so `--max-pages 200` (15/page) covers ~3,000 newest per category.
- [ ] **Step 5: Export + verify:** run the exporter to `data/interim/recrawl_2026-10/mogi.csv`; `python -m src.crawl.verify_sample data/interim/recrawl_2026-10/mogi.csv --n 25` → Mogi ≥95% link and image.
- [ ] **Step 6: Commit** code only (data is gitignored).

---

### Task 4: Alonhadat — resumable slow crawl

**Files:** Run only: `src/crawl/run_alonhadat.py` (no code change expected).

- [ ] **Step 1:** Run `python -m src.crawl.run_alonhadat --city hanoi --max-pages 20 --max-details 150` (20–40 s delay from `config/sources.yaml`; ~1–1.5 h). Do not shorten the delay.
- [ ] **Step 2:** If it prints `ChallengeEncountered`, **stop**, record count collected, and resume on a later day from the checkpoint (`data/alonhadat_seen_urls.db`). Partial output is acceptable; report the count.
- [ ] **Step 3:** Export via `src/export/export_alonhadat_to_sample.py` into `data/interim/recrawl_2026-10/alonhadat.csv`; verify with `verify_sample` (≥95%, else inspect failing rows — expired ads are expected to be rare on newest-first pages).

---

### Task 5: Phongtro123 — fix image extraction, fresh crawl

**Files:**
- Modify: `crawlers/phongtro123/src/parse/phongtro123_parser.py:172-180`
- Test: `crawlers/phongtro123/tests/` (add one test using a saved detail-page fixture)

- [ ] **Step 1:** Save one live detail page to `crawlers/phongtro123/tests/fixtures/` (via the project's Fetcher, robots-compliant) and open it: identify the CSS container of the main gallery vs. "tin tương tự"/related widgets.
- [ ] **Step 2: Failing test:** assert `parse(...)["image_urls"]` contains only gallery images (all share the main size path `thumbs/900x600` or the gallery container) and none of the related-ad thumbs (`thumbs/450x300`).
- [ ] **Step 3:** Restrict the `soup.find_all("img")` loop to the gallery container found in Step 1; drop the 8-image cap to 20; keep logo/icon filter. Run the test → PASS.
- [ ] **Step 4: Crawl:** `cd crawlers/phongtro123 && python scripts/crawl_all.py --site phongtro123` (Hanoi targets only: edit `TARGETS` run via flag if available, otherwise filter after) → export with `posted_at_raw` kept (needed for the freshness filter).
- [ ] **Step 5:** Copy output to `data/interim/recrawl_2026-10/phongtro123.csv`; verify ≥95%.

---

### Task 6: Chotot, Rencity, YourHome

**Nhatot (ex-Chotot)** — https://www.nhatot.com/ (`crawlers/chotot/crawler.ipynb`, API `gateway.chotot.com/v1/public/ad-listing`):
- Measured 2026-10-06: robots.txt allows `/` (disallows `*q=`, `*f=`, `*price=`, `/user/`, `*tin-dang-tuong-tu*`, …) but a plain `curl` to a detail page got **HTTP 403**. Do not scrape detail HTML or work around the block; use only the public JSON API the notebook already uses and **build** the link from `ad_id`. Task 2's checker must treat a 403 on this host as "unverifiable by script" and have it verified manually in the browser (2 links), not as a pass.
- [ ] Re-run the notebook for **Hanoi (region_v2 = Hà Nội)** phòng trọ only (as already configured in `config.py`; assert every row's `region`/`area_name` is Hà Nội before export); export `listing_url = https://www.nhatot.com/thue-phong-tro/<ad_id>` and `image_urls` as a clean JSON list from the `images` field (full-size URLs, not thumbs). Output `chotot.csv`; verify ≥95%.

**Rencity** — https://rencity.vn/ — investigated 2026-10-06, **permalink exists**:
- The site's own listing cards link to `/post/<slugified-title>-<id>` (found in its JS chunk `3943wrc82r9m2.js`). It is server-rendered: `/post/van-phong-...-32921` and `/post/x-32921` both return 200 with `<title>Rencity - <the ad's real title></title>`; a non-existent id (`/post/x-99999999`) returns 200 with an **empty** title. Only the trailing id matters. The old `search?post_id=N` is just the generic search page (`<title>Rencity - Tìm kiếm</title>`) and does **not** open the ad → stop using it.
- robots.txt (full file read): rules exist only for Googlebot/Applebot/Bingbot (`Disallow: /host`, `/mo-post`); no rule for `*`, so `/post/…` and the public API are not disallowed. Still never touch `/host` or `/mo-post`, keep delays ≥ 2 s.
- The API (`api1.renapp.vn/api/user/community/mo_posts?province_id=1`) is already Hà Nội-only and fresh: newest post was updated 2026-10-06 03:31; newest id 32921, whereas our current data stops near 32419 → ~500 new posts. It also returns non-room posts (e.g. "Văn phòng tầng 1 … 50m²" = an office): drop rows whose title starts with `Văn phòng|Mặt bằng|Cửa hàng` or house_type not a room.
- [ ] In `src/scrapers/crawl_rencity.py` change `post_url` to `https://rencity.vn/post/{slug(title)}-{id}` where `slug` = lowercase, `unicodedata` NFKD strip accents (`đ`→`d`), non-alphanumerics → `-`. Add a test in `tests/test_link_check.py`: `slug("Phòng 501 mới, đủ nội thất")` == `"phong-501-moi-du-noi-that"`.
- [ ] Re-run `python -m src.scrapers.crawl_rencity`; images come from the API `images` (S3 `rencity-bucket…webp`). In Task 2's checker, Rencity link passes only if the page `<title>` after `Rencity - ` is non-empty and shares ≥ 3 words with the row's title.

**YourHome** — https://yourhome.top/ — investigated 2026-10-06, **permalink exists**:
- Every room card links to `/room/<id>` (e.g. `https://yourhome.top/room/1791207671066`), the same `id` as in the embedded JSON the scraper already parses. The page is a client-rendered shell: it returns 200 for **any** id (`/room/123` too) with a generic title, so an HTTP check cannot prove the room exists. No robots.txt (404 page).
- [ ] In `src/scrapers/crawl_yourhome.py` add `post_url = f"https://yourhome.top/room/{id}"` to the CSV/JSON; keep `--city ha-noi` and drop rows whose `city` is not Hà Nội.
- [ ] Verification rule (Task 2): the id must appear in that same fresh crawl's list (proves it is a current room), plus the user opens 2 links in a browser. YourHome is reported as "link: id-verified, not HTTP-verified"; its images (`yourhome.top/images/room-image-…`) are still checked over HTTP.
- Only ~84 rooms, so low impact either way.

Commit any code/pattern changes.

---

### Task 7: Merge, gate and rebuild

**Files:**
- Modify: `src/recsys/prepare.py` (add step after dedup), `src/recsys/app.py:186` (button already guarded by `isinstance(str)`; also show placeholder when `image_urls` is empty)
- Test: `tests/test_ml.py` or new `tests/test_prepare_links.py`

- [ ] **Step 1: Failing test:** a frame with a Mogi `dummy-id` URL and a duplicated YourHome URL → after `prepare.gate_links(df)`, `listing_url` is `NaN` for both, a valid Chotot URL is kept, `image_urls` is always a JSON list string.
- [ ] **Step 2:** Implement `gate_links(df)` in `prepare.py`: `df.loc[mark_bad_links(df), "listing_url"] = np.nan`; `df["image_urls"] = df.image_urls.map(lambda v: json.dumps(parse_images(v)))`. Call it in the pipeline right after dedup. Run test → PASS.
- [ ] **Step 3:** Merge the new files in `data/interim/recrawl_2026-10/` + existing Facebook rows into `data/unified_hanoi_rentals.csv`'s successor via `src/pipelines/merge_crawl_results.py` (add the new directory as an input; do **not** overwrite the old file — write `data/unified_hanoi_rentals_2026-10.csv` and point `prepare.SRC` at it).
- [ ] **Step 4: Freshness:** in `prepare.py` drop rows with `days_old > 180` (phongtro123 only has dates) and exclude them from price-model training (they are removed before `price_model.enrich`). Rows without a date are kept (cannot judge).
- [ ] **Step 5:** `python -m src.recsys.prepare`, `python -m pytest tests -q`, Streamlit smoke test from CLAUDE.md. Commit.

---

### Task 8: Final acceptance

- [ ] `python -m src.crawl.verify_sample data/unified_hanoi_rentals_dedup.csv --n 25` → every non-Facebook platform ≥ 95% link and ≥ 95% image, exit 0. Save output as `data/interim/recrawl_2026-10/final.txt`.
- [ ] In the Streamlit app click "Xem tin" on 2 listings per platform and confirm each opens the matching ad (manual; the checker cannot judge "right ad" beyond id-in-URL and no-expiry).
- [ ] Report: rows per source before/after, share with permalink, share with ≥1 image, share with `days_old ≤ 180`, and which sources hit a challenge or have no permalink.

## Self-review

- Spec coverage: newest data (Tasks 3–6 crawl newest-first + Task 7 freshness filter), right link (Tasks 1, 3, 6, 7, 8), image collectable (Tasks 1, 5, 6, 8), Facebook excluded (Global Constraints).
- Open risks the plan cannot resolve without running: alonhadat CAPTCHA (partial yield), Rencity/YourHome may have no permalink, hotlink-blocking CDNs (Task 2/8 will surface it; fix would be an image proxy, out of scope until seen).
