"""Export the parsed Parquet corpus to CSV.

Parquet is the working format (typed, keeps list columns); CSV is for handing
the data to Excel / QGIS / a classmate. Two things this handles that a bare
df.to_csv() does not:

- **UTF-8 BOM.** Excel on Windows reads a plain UTF-8 CSV as ANSI and mangles
  every Vietnamese diacritic ("Quận Tân Phú" -> "QuÃ¡n TÃ¢n PhÃº"). Writing
  utf-8-sig fixes that, and is still plain UTF-8 to pandas/QGIS.
- **List columns.** image_urls is a list per row; CSV has no list type, so it
  is joined on " | ".

Usage:
    python -m src.export.to_csv
    python -m src.export.to_csv --only-geocoded -o data/processed/geo.csv
    python -m src.export.to_csv --no-description        # smaller file
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

REPO_ROOT = Path(__file__).resolve().parents[2]
IN_PATH = REPO_ROOT / "data" / "interim" / "parsed_mogi.parquet"
OUT_PATH = REPO_ROOT / "data" / "processed" / "mogi_listings.csv"

# lat/lon first after the identity columns -- this file exists to be mapped.
COLUMN_ORDER = [
    "listing_id", "source", "url",
    "lat", "lon", "geo_confidence",
    "province", "district", "address_raw",
    "title", "price_vnd_month", "price_raw", "price_is_negotiable",
    "area_m2", "room_type", "posted_at", "crawled_at",
    "n_images", "image_urls",
    "poster_name", "poster_id_hash", "phone_hash", "phone_prefix",
    "legal_status", "description",
]

log = logging.getLogger("to_csv")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-i", "--input", type=Path, default=IN_PATH)
    ap.add_argument("-o", "--output", type=Path, default=OUT_PATH)
    ap.add_argument("--only-geocoded", action="store_true",
                    help="Drop rows with no lat/lon.")
    ap.add_argument("--no-description", action="store_true",
                    help="Omit the description column (it is long and multi-line).")
    args = ap.parse_args()

    df = pd.read_parquet(args.input)
    log.info("read %d rows from %s", len(df), args.input)

    has_geo = df["lat"].notna() & df["lon"].notna()
    log.info("lat/lon present on %d/%d rows (%.1f%%)",
             has_geo.sum(), len(df), has_geo.mean() * 100)
    if args.only_geocoded:
        df = df[has_geo]
        log.info("--only-geocoded: kept %d rows", len(df))

    if "image_urls" in df.columns:
        df = df.copy()
        # Parquet round-trips a list column as numpy.ndarray, not list, and
        # pd.isna() on an array returns an array (not a bool) -- so test for
        # the sequence first and never call isna() on one.
        def _join(v: object) -> str:
            if isinstance(v, (list, tuple, np.ndarray)):
                return " | ".join(str(x) for x in v)
            return "" if pd.isna(v) else str(v)

        df["image_urls"] = df["image_urls"].apply(_join)

    cols = [c for c in COLUMN_ORDER if c in df.columns]
    cols += [c for c in df.columns if c not in cols]  # keep anything new
    if args.no_description and "description" in cols:
        cols.remove("description")
    df = df[cols]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig: see module docstring. newline="" so quoted multi-line
    # descriptions keep their line breaks intact rather than gaining \r\r\n.
    df.to_csv(args.output, index=False, encoding="utf-8-sig", lineterminator="\n")
    size_mb = args.output.stat().st_size / 1e6
    log.info("wrote %d rows x %d cols -> %s (%.1f MB)",
             len(df), len(cols), args.output, size_mb)


if __name__ == "__main__":
    main()
