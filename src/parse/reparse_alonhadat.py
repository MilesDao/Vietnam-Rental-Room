"""Rebuild data/interim/parsed_alonhadat.parquet from the retained raw HTML.

The crawler keeps every detail page gzipped under data/raw/html/alonhadat/<date>/,
independently of the Parquet, precisely so parsed output is disposable. Use
this when:

- a parser bug or an alonhadat markup change means the Parquet is wrong --
  re-parse instead of re-crawling (docs/alonhadat_scraping.md);
- PROJECT_SALT was rotated, so phone_hash/poster_id_hash need recomputing
  consistently across the whole corpus;
- the crawler was hard-killed (not Ctrl+C) and up to FLUSH_EVERY rows were
  still buffered: they are recorded 'fetched' in seen_urls and their raw HTML
  is on disk, but they never reached the Parquet.

Usage:
    python -m src.parse.reparse_alonhadat              # rebuild in place
    python -m src.parse.reparse_alonhadat --dry-run    # just report what it'd do
"""
from __future__ import annotations

import argparse
import gzip
import logging
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.parse.alonhadat_parser import parse_detail_page

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "html" / "alonhadat"
DB_PATH = REPO_ROOT / "data" / "alonhadat_seen_urls.db"
OUT_PATH = REPO_ROOT / "data" / "interim" / "parsed_alonhadat.parquet"

log = logging.getLogger("reparse_alonhadat")


def known_urls() -> dict[str, str]:
    """listing_id -> url, from the crawl's own record of what it fetched."""
    if not DB_PATH.exists():
        return {}
    with sqlite3.connect(DB_PATH) as conn:
        return dict(conn.execute("SELECT listing_id, url FROM seen_urls").fetchall())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="Report counts without writing the Parquet.")
    args = ap.parse_args()

    urls = known_urls()
    files = sorted(RAW_DIR.glob("*/*.html.gz"))
    log.info("%d raw pages on disk, %d urls known from seen_urls", len(files), len(urls))

    rows, missing_url, failed = [], 0, 0
    for path in files:
        listing_id = path.name[: -len(".html.gz")]
        url = urls.get(listing_id)
        if url is None:
            # The URL is only needed to recover the native id and to record
            # provenance; reconstruct a minimal one rather than dropping data.
            missing_url += 1
            url = f"https://alonhadat.com.vn/-{listing_id.removeprefix('alonhadat_')}.html"
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                rows.append(parse_detail_page(f.read(), url))
        except Exception:
            log.exception("failed to re-parse %s", path)
            failed += 1

    df = pd.DataFrame(rows).drop_duplicates(subset="listing_id", keep="last")
    log.info("parsed %d rows (%d unique) | %d had no url in seen_urls | %d failed",
             len(rows), len(df), missing_url, failed)

    if args.dry_run:
        existing = len(pd.read_parquet(OUT_PATH)) if OUT_PATH.exists() else 0
        log.info("dry run: Parquet currently holds %d rows, rebuild would hold %d",
                 existing, len(df))
        return

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(OUT_PATH)
    log.info("wrote %d rows -> %s", len(df), OUT_PATH)


if __name__ == "__main__":
    main()
