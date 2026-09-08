# Vietnam Rental Room — Data Pipeline, EDA & Map-Based Recommender

**Goal:** crawl rental-room listings (attributes + images) from Vietnamese classifieds,
build a clean analysable dataset, engineer features, run deep EDA, and finally serve a
recommendation system on an interactive map of Vietnam.

**Stack:** Python 3.12 · requests/httpx + BeautifulSoup/lxml (+ Playwright for JS pages) ·
pandas / polars · scikit-learn · Pillow + imagehash + PyTorch (CLIP/ResNet) ·
DuckDB or SQLite + Parquet · Folium / Streamlit / deck.gl · Jupyter.

**Assumptions (confirm before Phase 1 execution)**
- Target cities: Hanoi + Ho Chi Minh City first, then Da Nang / Hai Phong / Can Tho.
- **Tier 1 — structured classifieds (the ML backbone).** Priority order set by live recon
  on 2026-09-09 (see Phase 1): **1. Chotot** (public JSON API, 82 fields, coordinates
  included) → **2. phongtro123** (server-rendered, exactly the phòng trọ segment) →
  **3. alonhadat** (no bot protection at all) → **4. mogi** (server-rendered) →
  **✗ batdongsan — cut**, Cloudflare challenge blocks even its robots.txt.
- **Tier 2 — social (Facebook groups, Threads):** free-text posts, no schema. Treated as a
  *separate, smaller, information-extraction* corpus — see **Phase 2B**. Do not assume this
  tier is available until the access route in 2B.0 is settled; Tier 1 must stand alone.
- Target volume: Tier 1 30k–80k listings / 150k–400k images; Tier 2 2k–10k posts.
- Tier 1 is publicly visible listing data. Tier 2 is **personal data** and carries ToS,
  legal, and ethics obligations — phone numbers and poster identity are hashed at ingest,
  raw PII never leaves the ingest boundary.

---

## Phase 0 — Project setup & ground rules

**Tasks**
- [ ] `git init`; add `.gitignore` (data/, .env, `__pycache__`, ipynb checkpoints, images/).
- [ ] Create venv, `requirements.txt` / `pyproject.toml`, pin versions.
- [ ] Repo skeleton (below).
- [ ] `config/sources.yaml` — per-site: base URL, list-page pattern, pagination rule,
      CSS/XPath selectors, rate limit, enabled flag.
- [ ] Logging (`structlog` or stdlib) + a run-manifest per crawl (`run_id`, timestamp, counts).
- [ ] Decide storage: raw HTML → gzip on disk; parsed rows → Parquet; serving → DuckDB.

```
fund-data-science/
├─ docs/            PLAN.md, data_dictionary.md, report/
├─ config/          sources.yaml, geo.yaml, params.yaml
├─ src/
│  ├─ crawl/        fetcher.py, spiders/<site>.py, image_downloader.py
│  ├─ parse/        <site>_parser.py, normalize.py
│  ├─ clean/        dedup.py, outliers.py, impute.py
│  ├─ geo/          address_parser.py, geocode.py, admin_units.py
│  ├─ features/     tabular.py, text.py, image.py, spatial.py
│  ├─ eda/          plots.py, profile.py
│  ├─ recsys/       content.py, hybrid.py, rank.py, evaluate.py
│  └─ app/          streamlit_app.py, map.py
├─ data/
│  ├─ raw/          html/<site>/<date>/*.html.gz, images/<listing_id>/*.jpg
│  ├─ interim/      parsed_<site>.parquet
│  ├─ processed/    listings_clean.parquet, features.parquet, embeddings.npy
│  └─ external/     vn_admin_boundaries.geojson, POI, price indices
├─ notebooks/       01_eda_overview.ipynb ... 06_recsys_eval.ipynb
├─ tests/
└─ reports/figures/
```

**Deliverable:** runnable skeleton, `pytest` green on a smoke test.

---

## Phase 1 — Source reconnaissance & crawl policy

**Tasks**
- [ ] For each candidate site: read `/robots.txt`, note Terms of Service, record allowed paths
      and `Crawl-delay` in `docs/crawl_policy.md`.
- [ ] Identify per site whether content is server-rendered (fast path: requests+lxml) or
      JS-rendered (Playwright). Check for a hidden JSON API first — e.g. Chotot exposes
      `gateway.chotot.com/v1/public/ad-listing?cg=1010&...`, far cheaper than HTML parsing.
- [ ] Map the URL space: city → district → paginated list → listing detail.
- [ ] Hand-collect 20 sample detail pages per site; write down every field visible.
- [ ] Define the **canonical schema** (union of sites) → `docs/data_dictionary.md`.

**Canonical schema (v1)**

| field | type | notes |
|---|---|---|
| `listing_id` | str | `{source}_{site_native_id}` |
| `source`, `url`, `crawled_at` | str/ts | provenance |
| `title`, `description` | str | raw text, Vietnamese |
| `price_vnd_month` | float | normalized from "3,5 triệu/tháng" |
| `deposit_vnd`, `electricity_vnd_kwh`, `water_vnd` | float | often only in description |
| `area_m2` | float | |
| `room_type` | cat | phòng trọ / nhà nguyên căn / chung cư mini / ở ghép / căn hộ dịch vụ |
| `n_bedrooms`, `n_bathrooms`, `floor`, `n_floors` | int | |
| `address_raw` | str | as printed |
| `street`, `ward`, `district`, `province` | str | parsed + normalized |
| `lat`, `lon`, `geo_confidence` | float/cat | |
| `amenities` | list[str] | wifi, điều hòa, gác lửng, nóng lạnh, chỗ để xe, tự do giờ giấc, khép kín… |
| `furnishing` | cat | trống / cơ bản / đầy đủ |
| `poster_type`, `poster_id_hash`, `phone_hash` | str | hashed, never store raw phone |
| `posted_at`, `expires_at`, `n_views` | ts/int | if available |
| `image_urls`, `n_images`, `image_paths` | list | |
| **Tier 2 only** | | |
| `tier` | cat | `classified` / `social` — carry everywhere, split every analysis by it |
| `platform`, `group_id`, `group_name`, `permalink` | str | social provenance |
| `post_type` | cat | offer / seeker / broker / noise (2B.3) |
| `n_reactions`, `n_comments`, `n_shares` | int | engagement / demand signal |
| `extraction_method`, `extraction_confidence` | cat/float | per-field; regex vs NER vs LLM |
| `raw_text` | str | PII-stripped post body, kept for re-extraction |

### Recon results — measured 2026-09-09 (re-verify before Phase 2; defenses change)

| Site | HTTP (plain UA) | Bot protection | robots.txt | Render | Verdict |
|---|---|---|---|---|---|
| **nha.chotot.com / nhatot.com** | 301→200 | Cloudflare CDN, **no challenge** | `Allow: /`, sitemap index published | **Public JSON API** | ⭐ **Primary** |
| **phongtro123.com** | 200, 162 KB | Cloudflare CDN, **no challenge** | `Allow: /`, only query-params disallowed (`/api` blocked) | Server-rendered, 62 detail links/page | ⭐ **Primary** |
| **alonhadat.com.vn** | 200, 129 KB | **None** (bare IIS/ASP.NET) | Minimal; only `/publish/*`, `can-mua`, `can-thue` blocked | Fully server-rendered (25 price + 34 area tokens in raw HTML) | ✅ Secondary |
| **mogi.vn** | 200, 91 KB | Cloudflare CDN, no challenge | `Allow: /`, `/api/` + `/Property/` blocked; 4 sitemaps | Server-rendered, 51 detail links/page | ✅ Secondary |
| **batdongsan.com.vn** | **403** `Cf-Mitigated: challenge` | **Cloudflare interstitial — blocks browser UA too; even `/robots.txt` is unreadable** | Cannot be read without solving the challenge | — | ❌ **Cut** |

**Decision: drop batdongsan.com.vn.** You cannot read its crawl policy without defeating a bot
challenge, and defeating it is out of scope (see 2B.0). Its rental stock also skews to
apartments/houses, not phòng trọ — it is the wrong segment for this project anyway.

### ⭐ Key finding — Chotot has a public structured API

`GET https://gateway.chotot.com/v1/public/ad-listing?cg=<category>&limit=&o=&st=u`
returns JSON with **82 fields per ad**, verified live:

```
subject, body, price (numeric!), price_string, size, deposit, rooms, toilets,
furnishing_rent, street_name, ward_name, area_name (district), region_name,
latitude, longitude,          <-- exact coordinates, free
images[], number_of_images, list_time (epoch ms), account_id, seller_info,
ad_features, params, pty_characteristics, ...
```

Consequences for the plan:
- **Phase 4 geocoding largely disappears for this source** — coordinates ship with the data.
  Reserve the geocoding cascade for phongtro123/mogi/alonhadat/social.
- **Phase 3 price/area parsing is unnecessary here** — `price` and `size` arrive numeric.
  Still build the parsers; the other sources need them.
- `account_id` gives a clean broker/dedupe key without touching phone numbers.
- **Operational caveat:** `total` caps at `10000` (Elasticsearch max result window), so a
  single query cannot page past 10k ads. Slice the frontier by region × district × price band
  to enumerate the full inventory.
- [ ] Confirm the rental category codes (`cg=`) — 1010/1020/1050 all returned capped results;
      identify which maps to phòng trọ vs. nhà/căn hộ cho thuê and record in `sources.yaml`.

> ⚠️ **Compliance note:** Chotot's robots.txt carries
> `Content-Signal: search=yes, ai-input=yes, ai-train=no` — an explicit publisher preference
> against using the content to *train* models. Your project trains a price model, embeddings,
> and a recommender. This is a stated preference rather than a hard legal prohibition, and
> academic research sits differently from commercial training, but **raise it with your
> supervisor and record the decision** in `docs/data_collection_ethics.md`. A defensible
> posture: analysis + EDA freely, models trained for coursework only, no model weights or
> derived dataset published.

**Deliverable:** `config/sources.yaml` filled in + data dictionary + go/no-go per site.

---

## Phase 2 — Crawler implementation

**Tasks**
- [ ] `fetcher.py`: session pooling, realistic UA, `robots.txt` obedience,
      polite delay (1–3 s jittered) + concurrency cap (≤4 per host), exponential backoff on
      429/5xx, per-host circuit breaker, resumable via a `seen_urls` SQLite table.
- [ ] Stage A — **discovery**: walk list pages per city/district, collect detail URLs +
      list-level snippets. Store URL frontier in SQLite (`status`: new/fetched/failed).
- [ ] Stage B — **detail fetch**: download HTML/JSON, gzip to `data/raw/html/...`.
      *Always keep raw* so parsing can be re-run without re-crawling.
- [ ] Stage C — **image fetch**: for each listing download up to N=8 images, dedupe by URL,
      convert to JPEG, resize longest side to 640 px, store `data/raw/images/<listing_id>/i.jpg`.
      Record `content_length`, `sha256`, `width/height`, HTTP status.
- [ ] Stage D — **parse**: per-site parser → canonical rows → `data/interim/parsed_<site>.parquet`.
      Parsers must be pure functions of raw HTML so they're unit-testable on fixtures.
- [ ] Incremental re-crawl job: re-visit listings weekly to capture price changes and
      de-listing (gives a time dimension — valuable for EDA and for a "still available" filter).
- [ ] `tests/`: golden-file tests — fixture HTML in, expected dict out, for each site.

**Risks & mitigations**
- Cloudflare / DataDome → Playwright with a real browser profile, slower rate, or drop the site.
- Layout changes → parser tests fail loudly; keep raw HTML to reparse.
- IP blocks → hard-lower the rate first; do not attempt evasion beyond polite crawling.

**Deliverable:** `python -m src.crawl.run --site phongtro123 --city hanoi --max-pages N`
producing raw HTML, images, and a parsed Parquet; crawl stats logged.

---

## Phase 2B — Social sources (Facebook groups, Threads)

In Vietnam a large share of real rental supply never reaches classifieds — it lives in
Facebook groups (*"Tìm phòng trọ Hà Nội"*, *"Nhà trọ sinh viên …"*) and increasingly on
Threads. This tier is worth having, but it is a **different problem**: no fields, no schema,
just free text + photos in a comment thread. Budget it as an *information-extraction*
sub-project, not as more crawling.

### 2B.0 — Access route (decision gate — settle this BEFORE writing code)

| Route | What you get | Cost / constraint | Verdict |
|---|---|---|---|
| **A. Meta Content Library API** | Public FB Pages/Groups + Threads content, first-party, sanctioned | Academic-institution application via ICPSR; approval takes weeks–months; data is analysed **inside Meta's secure sandbox** — you generally cannot export raw rows or images into a local pipeline | The *legitimate* route. Verify current Threads coverage + export rules. Sandbox restriction may make it unusable for this project's image pipeline |
| **B. Graph API on a group you administer** | Full content of *your own* group | Must be group admin + approved Meta app; the open Groups read API was largely removed in 2021 | Clean and legal if you (or a course partner) admin a suitable group. Small n |
| **C. Manual / browser-assisted collection** | Anything you can see logged in | ToS violation; account-ban risk on *your* account; rate must stay human-scale; third-party scrapers (Apify actors, `facebook-scraper`) outsource the violation, don't remove it | Pragmatic for a few thousand posts. Use a throwaway-risk-tolerant account, never automate faster than a human, accept it may stop working |
| **D. Consented / self-collected** | Posts you or classmates author or export; group admin's blessing | Slow, tiny n | Good for building the *gold-standard labelled set* (2B.3) |

- [ ] Pick a route, record it and its justification in `docs/data_collection_ethics.md`.
- [ ] Check USTH's research-ethics requirement for human-subject/personal data before collecting.
- [ ] **Fallback plan:** if no route is viable, Phase 2B is cut and Tier 1 carries the project.
      Nothing downstream may depend on Tier 2 existing.

**Explicitly out of scope:** proxy rotation, browser-fingerprint spoofing, CAPTCHA solving,
account pools, or any other measure whose purpose is to avoid detection. If a source can only
be collected that way, drop the source.

### 2B.1 — Collection

- [ ] Define the group/hashtag frontier: 10–30 FB groups by city, Threads hashtags
      (`#phongtro`, `#chothuephong`, `#timphongtro`) + keyword search.
- [ ] Capture per post: `post_id`, `group_id`/`group_name`, `posted_at`, `text`,
      `image_urls`, `n_reactions`, `n_comments`, `n_shares`, `poster_id`, `permalink`.
- [ ] Capture **comments** too — in FB groups price negotiation, "còn phòng không?",
      and the actual address often live in comments, not the post body.
- [ ] Human-scale pacing: ≤1 request per 3–5 s, session breaks, no overnight unattended runs.
- [ ] Persist raw JSON/HTML exactly as fetched to `data/raw/social/<platform>/<date>/`.

### 2B.2 — PII boundary (do this at ingest, before anything is written to disk)

- [ ] `src/crawl/pii.py` runs on every record *before* persistence:
      phone → `sha256(phone + PROJECT_SALT)`, keep `phone_prefix` (carrier) only;
      poster name/id → salted hash; strip emails, Zalo IDs, profile URLs, avatar URLs.
- [ ] Keep a **local-only, gitignored, never-published** `id_map` if you need reversibility;
      otherwise don't keep one.
- [ ] Face handling in images: either skip images from Tier 2 entirely (simplest, recommended),
      or run a face detector and blur before storage. Never publish Tier 2 images in the report.
- [ ] Publishable artefact = aggregate statistics and hashed ids only.

### 2B.3 — Information extraction (the real technical work)

A typical group post has zero structure:

```
CHO THUÊ PHÒNG TRỌ NGÕ 173 HOÀNG HOA THÁM
- DT 25m2 có gác xép, khép kín
- Giá 3tr5/th, điện 4k/số, nước 100k/người
- Full đồ, máy giặt chung, tự do giờ giấc
- LH: 09xx.xxx.xxx
```

Build a cascade into the **same canonical schema as Tier 1**:

1. **Rule/regex baseline** — price (`3tr5`, `3.5tr`, `3triệu5`, `3500k`), area (`25m2`, `DT 25`),
   utilities (`điện 4k/số`), phone, amenity lexicon. Cheap, high precision, low recall.
2. **Vietnamese NER** for locations — `underthesea` / PhoBERT-based tagger to pull
   street / ngõ / ward / district mentions out of prose.
3. **LLM extraction pass** — few-shot prompt with the canonical JSON schema over each post.
   This is the right tool for noisy Vietnamese free text at this n (a few thousand posts is
   cheap). Force strict JSON output, validate against a Pydantic model, reject and retry
   malformed rows.
4. **Ensemble & confidence** — take the regex value when it fires, LLM otherwise; disagreement
   between the two flags the row for review. Store `extraction_method` + `extraction_confidence`
   per field so EDA can filter on them.
5. **Gold set & evaluation** — hand-label **300 posts** (route D is fine for this).
   Report **per-field precision / recall / F1** (price, area, district, amenities) and only
   admit fields that clear an agreed threshold (e.g. F1 ≥ 0.85) into the modelling dataset.
   *This evaluation table is a headline result of the project — it is what makes Tier 2
   defensible rather than decorative.*
- [ ] Post-type classifier: is this an **offer**, a **seeker** ("cần tìm phòng…"), a broker
      ad, or noise? Seeker posts are not supply — but they are a superb **demand signal**
      for the recommender and for EDA (Phase 6.8/6.11).

### 2B.4 — What Tier 2 adds that Tier 1 cannot

- **Demand side**: seeker posts → what budget/area/district people actually ask for.
- **Engagement**: reactions/comments as a proxy for listing attractiveness and market heat.
- **Freshness**: group posts lead classifieds by days.
- **Informal supply**: rooms that never appear on any classified site.
- **Negotiation signal**: comment threads reveal gap between asking and agreed price.

**Deliverable:** `data/interim/social_posts.parquet` (PII-hashed) +
`data/processed/social_extracted.parquet` conforming to the canonical schema +
`reports/extraction_eval.md` with the per-field F1 table + `docs/data_collection_ethics.md`.

---

## Phase 3 — Normalization & cleaning

**Tasks**
- [ ] **Price parsing**: `"3,5 triệu/tháng"`, `"3.500.000đ"`, `"350 nghìn"`, `"Thỏa thuận"`,
      `"$200"` → VND/month float + `price_is_negotiable` flag. Unit-test the parser hard.
- [ ] **Area parsing**: `"25m2"`, `"25 m²"`, `"20-25m2"` → float (+ `area_is_range`).
- [ ] **Text normalization**: Unicode NFC, strip emoji/decorative box chars, collapse
      whitespace, keep Vietnamese diacritics; also store an ASCII-folded copy for matching.
- [ ] **Address normalization**: map to official admin units. ⚠️ Vietnam reorganized its
      provincial/commune structure in 2025 (63 → 34 provinces, district level dissolved) — store
      **both** the legacy district label found in listings and the current admin code, with a
      crosswalk table in `data/external/`. Do not assume listing text uses the new units.
- [ ] **Amenity extraction** from free text: curated Vietnamese keyword/regex lexicon
      (`khép kín`, `tự do giờ giấc`, `gác xép`, `ban công`, `máy giặt`, `thang máy`, `chung chủ`…)
      → multi-hot columns. Manually validate on a 200-row sample; report precision/recall.
- [ ] **Missing values**: quantify per column; impute only where defensible
      (e.g. `n_bedrooms=1` for phòng trọ), never impute the target price — flag and drop.
- [ ] **Outliers**: price/m² winsorization by district; explicit rules for obvious
      typos (price < 200k or > 100M VND/month, area < 5 or > 500 m²). Keep an
      `is_outlier` + `outlier_reason` column rather than silently deleting.

### Deduplication (a core deliverable — do it in layers)
1. **Exact**: same `source` + native id; same canonical URL.
2. **Near-exact text**: MinHash/SimHash over normalized `title + description`
   (shingles of 5 tokens), LSH bucketing, Jaccard ≥ 0.85 → candidate pair.
3. **Attribute match**: same normalized address (or lat/lon within 50 m) **and**
   |area diff| ≤ 1 m² **and** |price diff| ≤ 5% → candidate pair.
4. **Image match**: perceptual hash (pHash + dHash, 64-bit) over every image;
   Hamming distance ≤ 6 between any image of A and any of B → strong duplicate signal.
   This is what catches the same room reposted with rewritten text across sites.
5. **Cross-post match (Tier 2)**: brokers post the *same room to 10+ groups* within minutes,
   with shuffled text. Add: same `phone_hash` **and** |price diff| ≤ 5% **and**
   |area diff| ≤ 1 m² **and** posted within 7 days → candidate pair. `phone_hash` is the
   single strongest dedupe key in social data — this is why Phase 2B.2 hashes rather than
   discards it.
6. **Resolution**: build a graph of candidate pairs, take connected components, pick a
   canonical record per cluster (most fields filled → most recent → Tier 1 preferred over
   Tier 2); keep `cluster_id`, `n_duplicates`, `duplicate_sources`, `n_groups_posted_to`
   as features (repost breadth signals a broker; repost frequency signals a hard-to-rent room).
- [ ] Report: how many dupes each layer caught, and a manually-checked 100-pair sample
      with precision/recall of the dedupe. Report Tier 1↔Tier 2 overlap separately — the
      share of social posts that also appear on classifieds is itself a finding.

**Deliverable:** `data/processed/listings_clean.parquet` + `reports/cleaning_report.md`
(before/after row counts, per-rule drop counts, dedupe stats).

---

## Phase 4 — Geocoding & spatial enrichment

**Tasks**
- [ ] Geocode `address_raw` → lat/lon. Cascade: (1) coordinates already in the page/JSON,
      (2) local gazetteer of VN streets/wards, (3) Nominatim (1 req/s, cache every response
      to SQLite) or Goong/Mapbox API if a key is available. Record `geo_confidence`
      (exact / street / ward / district centroid) — never silently pass off a district
      centroid as a rooftop coordinate.
- [ ] Reverse-check: geocoded point must fall inside the claimed district polygon; else flag.
- [ ] Load admin boundaries GeoJSON (province/ward) into `data/external/`.
- [ ] POI layer: universities (USTH, HUST, VNU, FTU…), hospitals, industrial parks,
      metro/BRT stops, big markets, CBD centroids. Source: OSM extract for Vietnam.
- [ ] Spatial features: distance to CBD, to nearest university, to nearest metro stop,
      to nearest hospital; H3 hex cell id (res 8/9) for aggregation; k-NN neighbour price
      statistics (median price/m² of 20 nearest listings, leakage-safe: exclude self).

**Deliverable:** geocoded Parquet + a first Folium map of listing density; geocode
success-rate table by city and confidence level.

---

## Phase 5 — Feature engineering & extraction

**5A. Tabular / derived**
- `price_per_m2`, `log_price`, `price_vs_district_median`, `price_percentile_in_ward`.
- `total_monthly_cost` = rent + est. electricity/water (parsed or district median).
- Rooms per m², `is_shared`, `has_private_bathroom`, `is_ground_floor`, `is_top_floor`.
- Temporal: `posted_month`, `day_of_week`, `days_listed`, `is_reposted`, `n_price_changes`
  (from the weekly re-crawl), season flags (academic year start Aug–Sep spikes demand).
- Target encoding / frequency encoding of ward & street (fit on train fold only).

**5B. Text features (Vietnamese)**
- Length, token count, uppercase ratio, emoji count, has-phone, has-price-in-text,
  ALL-CAPS-shout score → proxies for listing quality/professionalism.
- TF-IDF (word 1–2 gram, with `underthesea`/`pyvi` word segmentation) → SVD to 50–100 dims.
- Sentence embeddings: `keepitreal/vietnamese-sbert` or multilingual E5 → 384/768-d vectors
  (this is the backbone of content-based recommendation).
- Topic model (LDA or BERTopic) → interpretable listing themes for EDA.

**5C. Image features**
- Quality: resolution, blur (variance of Laplacian), brightness, colorfulness, aspect ratio,
  is-watermarked heuristic, count of images per listing.
- Content: CLIP (ViT-B/32) embeddings per image → mean-pool per listing (512-d).
- Zero-shot CLIP scene tagging: {bedroom, bathroom, kitchen, balcony, exterior/alley,
  floor plan, empty room, furnished room} → per-listing scene coverage flags.
- Optional supervised head: hand-label 500 images "furnished vs empty" / "clean vs cluttered",
  train a small classifier on CLIP features, propagate labels.
- Image-derived listing score = f(n_images, avg quality, scene coverage) — test whether it
  correlates with price and with days-listed.

**5D. Dimensionality & selection**
- PCA/UMAP for visualization; mutual information + permutation importance for selection.
- Assemble `data/processed/features.parquet` with a documented column list and
  a `feature_spec.yaml` recording every transform (so it's reproducible at serve time).

**Deliverable:** feature matrix + `docs/feature_catalog.md` describing each feature,
its rationale, and its computation.

---

## Phase 6 — Exploratory Data Analysis (go deep)

Organize as numbered notebooks, each exporting figures to `reports/figures/`.

1. **Data quality overview** — row/column counts, missingness heatmap, dtype audit,
   duplicates removed per layer, crawl coverage by city/district/source, collection timeline.
2. **Univariate** — distributions of price, area, price/m², n_images; log transforms;
   skew/kurtosis; heavy-tail check (log-normal vs power law fit for price).
3. **Bivariate** — price vs area (scatter + LOWESS, by room type); price vs district;
   price vs distance-to-CBD/university; correlation matrix (Spearman for monotone).
4. **Geospatial** — choropleth of median price/m² by ward; H3 hexbin heatmaps; listing
   density vs price; hotspot detection (Getis-Ord Gi*); Moran's I for spatial autocorrelation
   (justifies using spatial features in the model).
5. **Segmentation** — clustering (K-Means / HDBSCAN on scaled tabular + embeddings) →
   name the segments ("cheap student room near university", "serviced apartment CBD",
   "shared room", "mini-apartment with elevator"); profile each segment.
6. **Text analysis** — top n-grams by segment, amenity co-occurrence matrix,
   word clouds per price quartile, topic model results.
7. **Image analysis** — image-count distribution, quality vs price, scene composition by
   segment, sample grids per cluster, CLIP-embedding UMAP colored by price decile.
8. **Temporal** — postings per week, seasonality, price drift, days-on-market survival
   curves (Kaplan–Meier) by price bucket and district.
9. **Market pricing model as an EDA tool** — fit gradient boosting (LightGBM/XGBoost) to
   predict log price; use SHAP to quantify what actually drives price; residual analysis to
   surface **underpriced/overpriced listings** (this becomes a recommender feature).
10. **Tier comparison (social vs classified)** — does Facebook/Threads supply differ from
    classifieds in price, area, district mix, informality? Selection bias analysis: who posts
    where. Extraction-quality caveats applied to every Tier 2 chart (always split by `tier`,
    never silently pool them).
11. **Demand side (Tier 2 only)** — seeker posts: budget distribution people *ask* for vs
    prices *offered*, by district; the supply–demand gap map; engagement (reactions/comments)
    vs price and vs days-listed; market heat by group and by week.
12. **Findings memo** — 10–15 stated, evidence-backed findings with the figure that proves each.

**Deliverable:** notebooks 01–11 + `reports/eda_findings.md` + a figure pack.

---

## Phase 7 — Recommendation system

**Framing.** No user-interaction logs exist at the start, so this is a **cold-start,
content-based + constraint-filtering** problem, upgraded to hybrid once the app collects
implicit feedback.

**7.1 Baselines**
- Popularity / recency within a filtered set.
- Hard-filter + sort by value score (predicted price − actual price from Phase 6.9).

**7.2 Content-based core**
- Item vector = concat(scaled tabular, text SBERT, image CLIP, spatial) with per-block weights.
- Similarity: cosine on L2-normalized blocks; ANN index via FAISS/hnswlib for speed.
- "More like this" from any listing; "matches my profile" from a user-supplied query form
  (budget, area, preferred district/workplace, must-have amenities, commute tolerance).
- Natural-language query → SBERT embed the query → retrieve (semantic search in Vietnamese).

**7.3 Constraint & geo layer**
- Hard filters: budget ceiling, min area, required amenities, max commute distance.
- Commute-aware scoring: user gives a work/study address → isochrone or haversine/OSRM
  travel time; score decays with travel time.
- Diversity: MMR re-ranking so results aren't 10 rooms in the same building; cap per building/poster.

**7.4 Hybrid / learning-to-rank (once feedback exists)**
- Log clicks/saves/contacts in the app → implicit-feedback matrix.
- ALS or LightFM (hybrid, uses item features → handles cold start), or a LambdaMART re-ranker
  over candidate sets from 7.2.

**7.5 Evaluation**
- Offline proxy: hold out listings, treat same-cluster/same-user-saved items as relevant;
  Precision@k, Recall@k, MAP, NDCG@10, coverage, intra-list diversity, novelty.
- Cold-start ablation: text-only vs image-only vs tabular-only vs full.
- Human eval: 30 query scenarios, 3 annotators rate top-10 relevance 0–2 → report agreement.
- A/B-ready hooks in the app for later online evaluation.

**Deliverable:** `src/recsys/` with a `recommend(query, k) -> ranked listings` API,
an evaluation notebook, and a results table comparing all variants.

---

## Phase 8 — Interactive map application

**Tasks**
- [ ] Streamlit app (`src/app/streamlit_app.py`) with: filter sidebar, Folium/pydeck map of
      Vietnam, marker clustering, price choropleth toggle, listing cards with image carousel.
- [ ] "Set my workplace" pin → commute-time isochrone overlay → re-rank recommendations live.
- [ ] Detail panel: attributes, images, price-vs-market gauge (SHAP-explained: *why* this
      price), similar listings row.
- [ ] Heatmap layers: median price/m², listing density, value score (bargain map).
- [ ] Feedback capture (like / dislike / save) written to a local table → feeds Phase 7.4.
- [ ] Performance: precompute embeddings + ANN index, cache with `@st.cache_data`,
      serve tiles from DuckDB; keep p95 interaction < 1 s.

**Deliverable:** locally runnable app + a recorded demo GIF + deployment notes
(Streamlit Community Cloud / HF Spaces, with the dataset trimmed to fit).

---

## Phase 9 — Reproducibility, documentation, report

- [ ] Makefile / `invoke` tasks: `crawl → parse → clean → geocode → features → train → app`.
- [ ] `README.md`: what, how to run, screenshots, results summary.
- [ ] `docs/data_dictionary.md`, `docs/feature_catalog.md`, `docs/crawl_policy.md`.
- [ ] Data card + ethics section: source, robots/ToS compliance, rate limits, personal-data
      handling (phones hashed, no re-identification), known biases (urban skew, listings ≠
      transactions, asking price ≠ agreed price, duplicate/spam agent posts).
- [ ] Final report: problem → data → methods → EDA findings → recsys design → evaluation →
      limitations → future work. Slides + demo.
- [ ] Tag `v1.0`, archive dataset snapshot (Parquet + checksums).

---

## Suggested timeline (adjust to your course deadlines)

| Week | Focus | Exit criterion |
|---|---|---|
| 1 | Phase 0–1 + **2B.0 access decision** (start the ethics/API application *now* — it is the long pole) | Skeleton + sources.yaml + data dictionary + Tier 2 route chosen |
| 2–3 | Phase 2 | ≥10k listings + images crawled, parsers unit-tested |
| 3–4 | Phase 2B.1–2B.2 (parallel with above) | Social posts collected, PII boundary tested |
| 4–5 | Phase 2B.3 | IE cascade + 300-post gold set + F1 table |
| 5 | Phase 3 | Clean Parquet + cleaning report, dedupe validated (incl. cross-post) |
| 6 | Phase 4 | ≥85% geocoded with confidence labels, first map |
| 7 | Phase 5 | features.parquet + embeddings built |
| 8–9 | Phase 6 | 12 notebooks + findings memo (the graded EDA core) |
| 10–11 | Phase 7 | Content-based recommender + evaluation table |
| 12 | Phase 8 | Working map app |
| 13 | Phase 9 | Report, slides, demo |

## Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Anti-bot blocks main source | High | Multi-source design; Chotot JSON API fallback; polite rates; drop a site rather than evade |
| **Meta blocks / bans account (Tier 2)** | High | Tier 2 is strictly additive — Tier 1 must carry the project alone; human-scale pacing; use an account you can afford to lose; accept the source may die mid-project |
| **Meta Content Library sandbox blocks export** | High | Verify export rules *before* choosing route A; if raw rows can't leave the sandbox, fall back to route B/C/D or cut Tier 2 |
| **PDP Law / ethics non-compliance** | High | Hash PII at ingest boundary; no raw phone/name/avatar on disk; ethics note in report; get USTH sign-off before collecting |
| **IE extraction quality too low** | Medium | Gold set of 300 posts; admit only fields with F1 ≥ 0.85; carry `extraction_confidence` into every downstream analysis |
| Broker spam floods Tier 2 | Medium | `phone_hash` cross-post dedupe; post-type classifier drops broker/noise; cap posts per poster |
| Geocoding quality in VN | High | Confidence tiers; boundary sanity check; never treat centroid as exact |
| 2025 admin-unit reform mismatch | Medium | Store legacy + current codes with a crosswalk |
| Price text chaos ("thỏa thuận") | Medium | Explicit negotiable flag; exclude from price models |
| Image storage size | Medium | Cap 8 imgs/listing, resize 640 px, JPEG q80 |
| No user feedback for recsys | High | Cold-start content-based design from day 1; feedback capture in app |
| Scope creep | High | Phases 0–6 are the deliverable; 7–8 are the stretch |

## Open questions to settle before Phase 1

1. **Which Tier 2 route (A/B/C/D)?** This is the long pole — route A needs an institutional
   application started in week 1. Everything in Phase 2B branches on it.
2. Are you (or a classmate) an admin of any rental Facebook group? That unlocks route B.
3. Does USTH require research-ethics review for collecting personal data? Ask the course
   supervisor before collecting, not after.
4. Which cities and how many listings do you actually need for the course scope?
5. Do you have (or can you get) a Goong/Mapbox geocoding key, or is Nominatim-only acceptable?
6. GPU available for CLIP/SBERT, or should image/text features stay CPU-light?
7. Is the deliverable a report + notebooks, or must the app be deployed publicly?
   (If it is public, Tier 2 data almost certainly cannot ship with it.)
