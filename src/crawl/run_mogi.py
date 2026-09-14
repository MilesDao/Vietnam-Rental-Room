"""CLI entrypoint for crawling mogi.vn's phong-tro (rental room) category.

Usage:
    python -m src.crawl.run_mogi --city hanoi --max-pages 5
    python -m src.crawl.run_mogi --city all --categories all     # nationwide

Nationwide crawling walks a frontier of (province x category) slices -- 32
provinces x 4 phong-tro sub-category views, per config/sources.yaml. Big
provinces run past 2000 list pages, so discovery is interleaved with detail
fetching rather than done up front, parsed rows are flushed to Parquet
periodically, and per-slice page progress is checkpointed in SQLite. A run can
be interrupted (Ctrl+C) and resumed later without losing work or re-walking
pages it already covered.
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
import signal
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # allow `python src/crawl/run_mogi.py`

from src.crawl.fetcher import Fetcher, RateLimit, RetryPolicy
from src.crawl.spiders.mogi import iter_list_pages
from src.parse.mogi_parser import parse_detail_page

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "sources.yaml"
FLUSH_EVERY = 200  # parsed rows buffered before an atomic Parquet rewrite

log = logging.getLogger("run_mogi")

_stop = False


def _request_stop(signum, frame) -> None:  # noqa: ARG001
    """First Ctrl+C asks for a clean stop; a second one aborts immediately."""
    global _stop
    if _stop:
        raise KeyboardInterrupt
    _stop = True
    log.warning("stop requested -- finishing current listing, flushing, then exiting")


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)["mogi"]


# --------------------------------------------------------------------------
# state: seen listings + per-slice page frontier
# --------------------------------------------------------------------------
def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_urls (
            listing_id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            status TEXT NOT NULL,      -- fetched | failed
            last_attempt_at TEXT NOT NULL
        )
        """
    )
    # Page-level progress per (province, category) slice, so an interrupted
    # nationwide run resumes mid-province instead of re-walking 2000 pages.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS frontier (
            province TEXT NOT NULL,
            category TEXT NOT NULL,
            last_page_done INTEGER NOT NULL DEFAULT 0,
            exhausted INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT,
            PRIMARY KEY (province, category)
        )
        """
    )
    conn.commit()
    return conn


def slice_state(conn: sqlite3.Connection, province: str, category: str) -> tuple[int, bool]:
    row = conn.execute(
        "SELECT last_page_done, exhausted FROM frontier WHERE province=? AND category=?",
        (province, category),
    ).fetchone()
    return (0, False) if row is None else (row[0], bool(row[1]))


def mark_slice(conn: sqlite3.Connection, province: str, category: str,
               last_page_done: int, exhausted: bool) -> None:
    conn.execute(
        "INSERT INTO frontier (province, category, last_page_done, exhausted, updated_at) "
        "VALUES (?,?,?,?,?) ON CONFLICT(province, category) DO UPDATE SET "
        "last_page_done=excluded.last_page_done, exhausted=excluded.exhausted, "
        "updated_at=excluded.updated_at",
        (province, category, last_page_done, int(exhausted),
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def already_fetched(conn: sqlite3.Connection, listing_id: str) -> bool:
    row = conn.execute(
        "SELECT status FROM seen_urls WHERE listing_id = ?", (listing_id,)
    ).fetchone()
    return row is not None and row[0] == "fetched"


def mark_seen(conn: sqlite3.Connection, listing_id: str, url: str, status: str) -> None:
    conn.execute(
        "INSERT INTO seen_urls (listing_id, url, status, last_attempt_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(listing_id) DO UPDATE SET status=excluded.status, "
        "last_attempt_at=excluded.last_attempt_at",
        (listing_id, url, status, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------
def save_raw_html(raw_dir: Path, listing_id: str, html: str) -> Path:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = raw_dir / day
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{listing_id}.html.gz"
    with gzip.open(out_path, "wt", encoding="utf-8") as f:
        f.write(html)
    return out_path


def flush_rows(rows: list[dict], interim_path: Path) -> int:
    """Merge buffered rows into the Parquet atomically; return total row count.

    Written to a temp file and os.replace()d, so an interrupt mid-write can
    never truncate a corpus that took hours to collect.
    """
    if not rows:
        return 0
    new_df = pd.DataFrame(rows)
    if interim_path.exists():
        combined = pd.concat([pd.read_parquet(interim_path), new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset="listing_id", keep="last")
    else:
        combined = new_df
    interim_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = interim_path.with_suffix(".parquet.tmp")
    combined.to_parquet(tmp, index=False)
    os.replace(tmp, interim_path)
    return len(combined)


def write_manifest(manifest: dict, run_id: str) -> None:
    manifest_dir = REPO_ROOT / "data" / "interim" / "run_manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / f"mogi_{run_id}.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# --------------------------------------------------------------------------
def run(provinces: list[str], categories: list[str], max_pages: int | None,
        max_details: int | None) -> None:
    cfg = load_config()
    run_id = uuid.uuid4().hex[:8]
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()

    fetcher = Fetcher(
        user_agent=cfg["user_agent"],
        robots_txt_url=cfg["robots_txt"],
        rate_limit=RateLimit(
            min_delay_s=cfg["rate_limit"]["min_delay_s"],
            max_delay_s=cfg["rate_limit"]["max_delay_s"],
        ),
        retry=RetryPolicy(
            max_attempts=cfg["retry"]["max_attempts"],
            backoff_base_s=cfg["retry"]["backoff_base_s"],
            retry_on_status=tuple(cfg["retry"]["retry_on_status"]),
        ),
    )

    db = init_db(REPO_ROOT / "data" / "mogi_seen_urls.db")
    raw_dir = REPO_ROOT / "data" / "raw" / "html" / "mogi"
    interim_path = REPO_ROOT / "data" / "interim" / "parsed_mogi.parquet"

    buf: list[dict] = []
    n_fetched = n_failed = n_skipped = n_pages = 0
    total_rows = 0

    def flush(force: bool = False) -> None:
        nonlocal buf, total_rows
        if buf and (force or len(buf) >= FLUSH_EVERY):
            total_rows = flush_rows(buf, interim_path)
            log.info("FLUSH +%d rows -> corpus now %d listings", len(buf), total_rows)
            buf = []

    def budget_spent() -> bool:
        return max_details is not None and n_fetched >= max_details

    slices = [(p, c) for p in provinces for c in categories]
    log.info("frontier: %d slices (%d provinces x %d categories)",
             len(slices), len(provinces), len(categories))

    try:
        for si, (province, category) in enumerate(slices, 1):
            if _stop or budget_spent():
                break
            last_done, exhausted = slice_state(db, province, category)
            if exhausted and max_pages is None:
                log.info("[%d/%d] %s / %s already exhausted -- skipping",
                         si, len(slices), province, category)
                continue
            start_page = last_done + 1
            log.info("[%d/%d] === %s / %s (from page %d) ===",
                     si, len(slices), province, category, start_page)

            reached_end = True
            try:
                for page, cards in iter_list_pages(
                    fetcher, cfg["base_url"], category, province,
                    start_page=start_page, max_pages=max_pages,
                ):
                    n_pages += 1
                    page_complete = True
                    for card in cards:
                        if _stop or budget_spent():
                            # Stopped part-way through this page: leave
                            # last_page_done at page-1 so the resume re-walks it
                            # and picks up the cards we never reached. Re-walking
                            # costs one list request; already_fetched() skips the
                            # details we did get.
                            page_complete = False
                            break
                        listing_id, url = card["listing_id"], card["url"]
                        if already_fetched(db, listing_id):
                            n_skipped += 1
                            continue
                        try:
                            resp = fetcher.get(url)
                            save_raw_html(raw_dir, listing_id, resp.text)
                            buf.append(parse_detail_page(resp.text, url))
                            mark_seen(db, listing_id, url, "fetched")
                            n_fetched += 1
                        except Exception:
                            log.exception("failed to fetch/parse %s", url)
                            mark_seen(db, listing_id, url, "failed")
                            n_failed += 1
                        flush()
                    if page_complete:
                        mark_slice(db, province, category, page, exhausted=False)
                    if n_pages % 10 == 0:
                        rate = n_fetched / max(time.monotonic() - started, 1) * 3600
                        log.info("progress: %d pages | %d fetched, %d skipped, %d failed "
                                 "| ~%.0f listings/h", n_pages, n_fetched, n_skipped,
                                 n_failed, rate)
                    if _stop or budget_spent():
                        reached_end = False
                        break
            except Exception:
                log.exception("slice %s / %s aborted", province, category)
                reached_end = False

            if reached_end and max_pages is None and not _stop:
                mark_slice(db, province, category,
                           slice_state(db, province, category)[0], exhausted=True)
                log.info("slice %s / %s EXHAUSTED", province, category)
    except KeyboardInterrupt:
        log.warning("hard interrupt -- flushing what is buffered")
    finally:
        flush(force=True)
        manifest = {
            "run_id": run_id,
            "site": "mogi",
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": round(time.monotonic() - started, 1),
            "provinces": provinces,
            "categories": categories,
            "max_pages": max_pages,
            "max_details": max_details,
            "n_list_pages": n_pages,
            "n_fetched": n_fetched,
            "n_failed": n_failed,
            "n_skipped_already_seen": n_skipped,
            "corpus_rows_after_run": total_rows,
            "stopped_early": _stop,
        }
        write_manifest(manifest, run_id)
        log.info("run manifest: %s", json.dumps(manifest, ensure_ascii=False))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    cfg = load_config()
    all_provinces: list[str] = cfg["provinces"]
    all_categories: list[str] = cfg["category_paths"]

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--city", default="hanoi",
                    help="'all' for every province in config, a CLI alias (hanoi, hcmc), "
                         "or a comma-separated list of mogi province slugs "
                         "(e.g. ha-noi,da-nang).")
    ap.add_argument("--categories", default="all",
                    help="'all' for every phong-tro sub-category, or a comma-separated list.")
    ap.add_argument("--max-pages", type=int, default=None,
                    help="Cap list pages walked per slice (default: walk to the end).")
    ap.add_argument("--max-details", type=int, default=None,
                    help="Cap detail pages fetched this run, across all slices.")
    args = ap.parse_args()

    aliases: dict[str, str] = cfg.get("cities", {})
    if args.city == "all":
        provinces = all_provinces
    else:
        provinces = []
        for tok in args.city.split(","):
            tok = tok.strip()
            slug = aliases.get(tok, tok)
            if slug not in all_provinces:
                ap.error(f"unknown province {tok!r} (slug {slug!r}); "
                         f"known: {', '.join(all_provinces)}")
            provinces.append(slug)

    if args.categories == "all":
        categories = all_categories
    else:
        categories = [c.strip() for c in args.categories.split(",")]
        for c in categories:
            if c not in all_categories:
                ap.error(f"unknown category {c!r}; known: {', '.join(all_categories)}")

    run(provinces, categories, args.max_pages, args.max_details)


if __name__ == "__main__":
    main()
