# Facebook Public Group Crawler — Hà Nội Rental Listings

A read-only crawler that collects **publicly visible posts** from public Facebook
groups (built for Hà Nội rental-housing groups) and saves them to JSONL/CSV, then
merges and geocodes them to a district-level lat/long.

## What it does

- Drives a real, logged-in Chrome (via the DevTools Protocol) and scrolls the
  group feed, extracting each post with in-page JavaScript.
- Handles Facebook's "comet" SPA DOM: recovers post ids from `posts/`,
  `pcb.`, `story_fbid`, or `multi_permalinks`; pulls text, timestamp, reaction
  count, and post images.
- De-duplicates (`post_url → post_id → text+timestamp hash`), saves incrementally
  (crash-safe, restartable), and bounds memory on long runs.
- Merges multiple groups into one dataset and attaches a Hà Nội **district
  centroid** latitude/longitude to every row.

## Setup

Requires **Python 3.11+**.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Authentication (CDP mode)

Log into a Chrome you control; the crawler attaches to it (never sees your
password).

```bash
# 1) start a dedicated Chrome with remote debugging, log into Facebook in it
google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/.fb-crawler-chrome"
```

`config.yaml` already points at it (`browser.cdp_url: "http://127.0.0.1:9222"`).

## Run

```bash
# sanity check: dump one screen of extracted posts, then exit
python -m src.crawler --config config.yaml --inspect

# crawl one group (target set by config max_posts / --max-posts)
python -m src.crawler --config config.yaml --group-url "https://www.facebook.com/groups/<ID>" --max-posts 1300

# crawl several groups, each into data/<slug>/
python -m src.multi --config config.yaml --max-posts 1300 \
  --groups https://www.facebook.com/groups/<ID_A> \
           https://www.facebook.com/groups/<ID_B>

# merge all groups + geocode -> data/posts_combined.csv / .jsonl
python -m scripts.build_combined
```

## Structured rental extraction (DeepSeek, optional)

`src.rental_pipeline` turns the combined crawl into a structured 31-column
rental table using the DeepSeek API. It classifies each post, skips non-rental
content (with an audit reason), and expands one post into one row per distinct
house-type × monthly-price.

```bash
cp .env.example .env          # then put your key in DEEPSEEK_API_KEY (.env is gitignored)
python -m src.rental_pipeline --limit 20     # small live test first
python -m src.rental_pipeline                 # full run over data/posts_combined.csv
```

Defaults: input `data/posts_combined.csv` → output `data/facebook_rentals_parsed.csv`
(plus a JSONL cache, audit log, and validation report). Never put the key in
`config.yaml`, commands, or source — only in `.env`.

## Data schema

Per post (JSONL / CSV columns):

| field | meaning |
|---|---|
| `post_id`, `post_url` | numeric id + canonical permalink (else `null`) |
| `group_url`, `group_name` | source group |
| `timestamp_text`, `timestamp` | displayed label; ISO time only if shown |
| `text` | full post text (Vietnamese Unicode / emoji / line breaks preserved) |
| `reaction_count`, `comment_count`, `share_count` | integers, else `null` |
| `image_urls`, `video_urls` | deduped media URLs (JSON strings in CSV) |
| `crawl_time` | ISO collection time |
| `district`, `ward` | detected Hà Nội admin area (else `null`) |
| `latitude`, `longitude`, `geo_precision` | district centroid; `geo_precision` ∈ {`district`,`city`} |

Unavailable values are `null` — never invented.

## Included dataset

`data/posts_combined.csv` — **5,747** unique posts across 4 Hà Nội rental groups
(per-group `data/<slug>/posts.csv` also included). Coverage: text 100%,
permalink/id ~81%, images ~86%, district-level geocode ~85%.

| group | posts |
|---|---|
| Tìm Phòng Trọ - Nhà Trọ Cho Sinh Viên Tại Hà Nội (`1164344644748784`) | 2,153 |
| Phòng Trọ Hà Nội Giá Rẻ (`nhatrohngiare`) | 1,240 |
| Cho Thuê Phòng Trọ - Nhà Trọ - Tìm Người Ở Ghép Hà Nội (`386158839291937`) | 1,199 |
| CHO THUÊ NHÀ VÀ PHÒNG TRỌ HÀ NỘI (`6603021829726413`) | 1,155 |

`data/facebook_rentals_geocoded_offline_full.csv` — the final structured rental
table (DeepSeek extraction expanded to one row per house-type × price), with
addresses geocoded **offline against an OpenStreetMap extract**. It is included
as a prepared artifact; the offline OSM geocoding step (which requires a local
Hà Nội `.osm.pbf` and `pyosmium`) is not part of this repo.

## Layout

```
config.yaml            # group URL, caps, delays, CDP settings, paths
src/
  crawler.py           # browser control, scroll loop, safety stops, CLI
  parser.py            # all Facebook-DOM logic (injected JS + normalization)
  exporter.py          # JSONL append, checkpoint, CSV, validation report
  utils.py             # count/URL/text normalization, dedup, logging
  multi.py             # crawl several groups, isolated per-group output
  geocode.py           # offline Hà Nội district-centroid geocoder
  hanoi_locations.py   # district/ward vocabulary
  rental_pipeline.py   # DeepSeek extraction -> 31-column rental table (optional)
  deepseek_rental_parser.py   # DeepSeek API client + prompt
  rental_schema.py     # output schema, row expansion, validation
scripts/build_combined.py   # merge groups + geocode -> combined dataset
data/                       # committed CSV outputs
```
