"""Clean the Hanoi flat-schema CSVs and fill in missing coordinates.

Usage:
    python -m src.clean.run_clean_hanoi_csv --dry-run         # counts only; sends nothing, writes nothing
    python -m src.clean.run_clean_hanoi_csv                   # clean, geocode, write outputs
    python -m src.clean.run_clean_hanoi_csv --no-geocode      # clean only
    python -m src.clean.run_clean_hanoi_csv --max-requests 50 # cap new Nominatim requests this run

Inputs, at the repo root and never modified: mogi_hanoi_extracted.csv,
alonhadat_hanoi_extracted.csv, sample.csv (the 31-column flat schema; rules in
src/clean/sample_schema.py).

Outputs:
    data/processed/hanoi_listings_clean.csv   every kept row from all inputs
    data/processed/<input>_clean.csv          the same rows, one file per input
    reports/hanoi_csv_cleaning_report.md      counts, flags, coordinate sources

Geocoding uses the public Nominatim API under its usage policy (see
src/geo/nominatim.py). Every response is cached in
data/external/nominatim_cache.sqlite, so a re-run only sends new queries.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.clean.sample_schema import READ_DTYPES, SAMPLE_COLUMNS, clean_sample_frame, mark_duplicates
from src.geo.address import build_candidates
from src.geo.nominatim import ATTRIBUTION, DEFAULT_USER_AGENT, NominatimBlocked, NominatimGeocoder

REPO_ROOT = Path(__file__).resolve().parents[2]
INPUTS = ["mogi_hanoi_extracted.csv", "alonhadat_hanoi_extracted.csv", "sample.csv"]
OUT_DIR = REPO_ROOT / "data" / "processed"
COMBINED_PATH = OUT_DIR / "hanoi_listings_clean.csv"
REPORT_PATH = REPO_ROOT / "reports" / "hanoi_csv_cleaning_report.md"
CACHE_PATH = REPO_ROOT / "data" / "external" / "nominatim_cache.sqlite"
ADDED_COLUMNS = [
    "source_file", "district_raw", "area_m2_min", "area_m2_max", "area_is_range",
    "price_missing", "area_missing", "is_outlier", "outlier_reason", "n_duplicates",
    "latitude_orig", "longitude_orig", "coord_issue", "geo_source", "geo_confidence", "geo_query",
]
GEO_LEVELS = ["listing", "alley", "street", "ward", "district", "city", "not_found", "not_attempted"]

log = logging.getLogger("run_clean_hanoi_csv")


def _key(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def load_inputs() -> pd.DataFrame:
    frames = [
        pd.read_csv(REPO_ROOT / name, dtype=READ_DTYPES, encoding="utf-8-sig").assign(source_file=name)
        for name in INPUTS
    ]
    return pd.concat(frames, ignore_index=True)


def address_groups(df: pd.DataFrame) -> dict[tuple, list[int]]:
    """Rows lacking a usable coordinate, grouped by (address, ward, district)."""
    groups: dict[tuple, list[int]] = {}
    for idx in df.index[df["coord_issue"].notna()]:
        key = (_key(df.at[idx, "address"]), _key(df.at[idx, "ward"]), _key(df.at[idx, "district"]))
        groups.setdefault(key, []).append(idx)
    return groups


def geocode_missing(df: pd.DataFrame, geocoder: NominatimGeocoder) -> str | None:
    """Fill coordinates in place. Returns why geocoding stopped early, if it did."""
    groups = address_groups(df)
    df.loc[df["coord_issue"].notna(), "geo_confidence"] = "not_attempted"
    log.info("geocoding %d distinct addresses (%d rows)", len(groups), sum(map(len, groups.values())))
    try:
        for n, (key, rows) in enumerate(groups.items(), 1):
            result, complete = geocoder.geocode(build_candidates(*key))
            if not complete:
                return f"request budget reached after {geocoder.n_requests} requests"
            if result is None:
                df.loc[rows, "geo_confidence"] = "not_found"
            else:
                df.loc[rows, "latitude"] = result.lat
                df.loc[rows, "longitude"] = result.lon
                df.loc[rows, "geo_source"] = "nominatim"
                df.loc[rows, "geo_confidence"] = result.level
                df.loc[rows, "geo_query"] = result.query
            if n % 25 == 0:
                log.info("%d/%d addresses | %d requests sent, %d cache hits",
                         n, len(groups), geocoder.n_requests, geocoder.n_cache_hits)
    except NominatimBlocked as exc:
        log.error("Nominatim refused service (%s) -- stopping. Cached results are kept; "
                  "re-run later rather than retrying now.", exc)
        return f"Nominatim refused service ({exc})"
    except KeyboardInterrupt:
        log.warning("interrupted -- writing what was geocoded so far")
        return "interrupted"
    return None


def dry_run(df: pd.DataFrame, geocoder: NominatimGeocoder) -> None:
    groups = address_groups(df)
    first, every, districts = set(), set(), set()
    from_cache = 0
    for key in groups:
        candidates = build_candidates(*key)
        if candidates:
            first.add((candidates[0].query, candidates[0].district))
        every.update((c.query, c.district) for c in candidates)
        districts.update(c.district for c in candidates if c.district)
        from_cache += geocoder.geocode(candidates)[1]
    log.info("dry run: %d rows lack coordinates, %d distinct addresses, %d resolvable from cache already",
             sum(map(len, groups.values())), len(groups), from_cache)
    log.info("dry run: between %d and %d requests before caching (1.1 s each: %.0f-%.0f min)",
             len(first) + len(districts), len(every) + len(districts),
             (len(first) + len(districts)) * 1.1 / 60, (len(every) + len(districts)) * 1.1 / 60)


def write_outputs(kept: pd.DataFrame) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    table = kept[SAMPLE_COLUMNS + ADDED_COLUMNS]
    table.to_csv(COMBINED_PATH, index=False, encoding="utf-8-sig")
    for name in INPUTS:
        table[table["source_file"] == name].to_csv(
            OUT_DIR / f"{Path(name).stem}_clean.csv", index=False, encoding="utf-8-sig"
        )


def write_back(cleaned: pd.DataFrame, repo_root: Path = REPO_ROOT,
               inputs: list[str] | None = None) -> list[Path]:
    """Copy the filled coordinates into the original CSVs, leaving every other column alone.

    Row order survives load_inputs() -> clean_sample_frame() -> mark_duplicates(),
    so row i of a file's slice is row i of that file on disk; the row count is
    checked before anything is written. Pass `cleaned` (not the deduplicated
    frame): the originals keep their duplicate rows and need coordinates too.
    A `.bak` copy is made the first time and never overwritten afterwards, so
    re-running can't turn the backup into an already-modified file.
    """
    written = []
    for name in inputs if inputs is not None else INPUTS:
        path = repo_root / name
        rows = cleaned[cleaned["source_file"] == name]
        raw = path.read_bytes()
        encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
        original = pd.read_csv(path, dtype=str, encoding=encoding, keep_default_na=False)
        if len(original) != len(rows):
            raise ValueError(f"{name}: {len(original)} rows on disk but {len(rows)} cleaned rows")
        backup = path.with_name(path.name + ".bak")
        if not backup.exists():
            backup.write_bytes(raw)
        original["latitude"] = [f"{v:.7f}" if pd.notna(v) else "" for v in rows["latitude"]]
        original["longitude"] = [f"{v:.7f}" if pd.notna(v) else "" for v in rows["longitude"]]
        original["geo_confidence"] = ["" if pd.isna(v) else str(v) for v in rows["geo_confidence"]]
        original.to_csv(path, index=False, encoding=encoding)
        written.append(path)
    return written


def _table(header: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return lines


def write_report(cleaned: pd.DataFrame, kept: pd.DataFrame, geocoder: NominatimGeocoder | None,
                 stopped: str | None, written_back: list[Path] | None = None) -> None:
    platforms = sorted(cleaned["platform"].dropna().unique()) + ["**total**"]

    def part(df: pd.DataFrame, platform: str) -> pd.DataFrame:
        return df if platform == "**total**" else df[df["platform"] == platform]

    lines = [
        "# Hanoi CSV cleaning report", "",
        f"Run at: {datetime.now(timezone.utc).isoformat()}", "",
        "Inputs (not modified): " + ", ".join(f"`{name}`" for name in INPUTS), "",
        "Outputs: `data/processed/hanoi_listings_clean.csv`, plus one `data/processed/<input>_clean.csv` "
        "per input. Built by `python -m src.clean.run_clean_hanoi_csv`; rules in "
        "`src/clean/sample_schema.py`, geocoding in `src/geo/`.", "",
        "## Rows", "",
    ]
    rows = []
    for p in platforms:
        c, k = part(cleaned, p), part(kept, p)
        rows.append([p, len(c), int(c["duplicate_of"].notna().sum()), len(k),
                     int(k["price_missing"].sum()), int(k["area_missing"].sum()),
                     int(k["area_is_range"].sum()), int(k["is_outlier"].sum())])
    lines += _table(["platform", "rows in", "duplicates removed", "rows out", "price missing",
                     "area missing", "area was a range", "outliers flagged"], rows)
    reasons = kept["outlier_reason"].dropna().str.split(";").explode().value_counts()
    lines += ["", "Outlier reasons (flagged, not removed): "
              + (", ".join(f"`{r}` {n}" for r, n in reasons.items()) or "none"), ""]

    lines += ["## Coordinates", "", "Rows out, by where their coordinate came from:", ""]
    rows = []
    for p in platforms:
        k = part(kept, p)
        counts = k["geo_confidence"].value_counts()
        rows.append([p, int((k["coord_issue"] == "outside_hanoi").sum()),
                     *(int(counts.get(level, 0)) for level in GEO_LEVELS)])
    lines += _table(["platform", "placeholder coords removed", *GEO_LEVELS], rows)
    lines += [
        "",
        "- `listing`: published by the platform; precision unknown (many mogi rows share one ward-level point).",
        "- `alley`: a point on the named ngõ off the named street.",
        "- `street`: a point on the named street inside the old district's bounding box. "
        "On a long street it can be a kilometre or more from the room.",
        "- `ward` / `district`: the centre of that ward's or old district's boundary "
        "(OpenStreetMap keeps pre-2025 units as historic boundaries).",
        "- `city`: the centre of a province outside Hanoi, for a stray non-Hanoi listing.",
        "- `not_found`: no query returned a matching place; latitude/longitude stay empty.",
        "- `not_attempted`: geocoding was skipped or stopped before reaching this address.",
        "",
        "Filter on `geo_confidence` before using coordinates for distances: `ward` and `district` "
        "points are area centres, not the room.",
        "",
        "## Geocoding", "",
    ]
    if geocoder is None:
        lines.append("- Not run.")
    else:
        lines += [
            f"- Requests sent this run: {geocoder.n_requests}; answered from cache: {geocoder.n_cache_hits}.",
            "- Cache: `data/external/nominatim_cache.sqlite`; a re-run only sends queries not in it.",
            "- Service: the public Nominatim API, used under its usage policy "
            "(https://operations.osmfoundation.org/policies/nominatim/): at most 1 request/second, "
            "single thread, cached, identifying User-Agent. Queries contain street, alley, ward and "
            "district names only -- no house numbers, phone numbers or names.",
        ]
    if stopped:
        lines.append(f"- Stopped early: {stopped}.")
    if written_back:
        lines.append(
            "- Coordinates and `geo_confidence` were also written into the original CSVs ("
            + ", ".join(f"`{p.name}`" for p in written_back)
            + "); each untouched original is kept beside it as `<name>.bak`."
        )
    lines += [
        "", f"**Attribution:** {ATTRIBUTION}. Credit this wherever these coordinates are published.", "",
        "## Rules applied", "",
        "- Text fields: Unicode NFC, emoji and control characters removed, whitespace collapsed.",
        "- `district`: mapped to one of Hanoi's 30 pre-2025 district-level units; anything else "
        "(e.g. \"Chưa rõ\") becomes empty. The original is kept in `district_raw`.",
        "- `ward`: taken from the address when it names one (mogi's ward column held a breadcrumb "
        "label, not a ward). Bare names in a quận get \"Phường\". Legacy and 2025 ward names both occur.",
        "- `price_vnd` of 0 or less becomes empty with `price_missing` true (every PhongTot row). Rows are kept.",
        "- `area_m2`: ranges such as \"20 - 27\" become their midpoint, with `area_m2_min`, `area_m2_max` "
        "and `area_is_range`; unusable values become empty with `area_missing` true.",
        "- Outliers are flagged in `is_outlier`/`outlier_reason`, never removed: price under 200k or "
        "over 100M VND, area under 5 or over 500 m², or price per m² outside 3×IQR for its district.",
        "- `contact_phone` / `contact_zalo` hold the project's salted phone hash (`src/crawl/pii.py`), "
        "computed after normalizing the number. No raw phone number is written.",
        "- Coordinates outside Hanoi are placeholders (central Ho Chi Minh City, the centre of Vietnam, "
        "a Web Mercator map corner) and are replaced; originals stay in `latitude_orig`/`longitude_orig`.",
        "- Duplicates: same platform and district, price within 5% and area within 1 m², and the same "
        "title or the same address with a house/alley number. The row with the most filled fields is "
        "kept and `n_duplicates` counts what was folded into it. Matches across platforms are kept.",
        "",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="Clean in memory and estimate geocoding requests; send nothing, write nothing.")
    ap.add_argument("--no-geocode", action="store_true", help="Clean only; leave missing coordinates empty.")
    ap.add_argument("--max-requests", type=int, default=None,
                    help="Stop geocoding after this many new Nominatim requests.")
    ap.add_argument("--write-back", action="store_true",
                    help="Also fill latitude/longitude/geo_confidence in the original CSVs at the "
                         "repo root, keeping every other column and a .bak copy of each.")
    args = ap.parse_args()

    cleaned = mark_duplicates(clean_sample_frame(load_inputs()))
    n_duplicates = int(cleaned["duplicate_of"].notna().sum())
    log.info("%d rows in, %d same-platform duplicates, %d rows out",
             len(cleaned), n_duplicates, len(cleaned) - n_duplicates)
    user_agent = os.environ.get("NOMINATIM_USER_AGENT", DEFAULT_USER_AGENT)

    if args.dry_run:
        dry_run(cleaned, NominatimGeocoder(CACHE_PATH, user_agent, offline=True))
        return

    geocoder, stopped = None, None
    if args.no_geocode:
        cleaned.loc[cleaned["coord_issue"].notna(), "geo_confidence"] = "not_attempted"
    else:
        # Geocode before dropping duplicates: those rows stay in the originals,
        # so --write-back needs coordinates for them too.
        geocoder = NominatimGeocoder(CACHE_PATH, user_agent, max_requests=args.max_requests)
        stopped = geocode_missing(cleaned, geocoder)

    kept = cleaned[cleaned["duplicate_of"].isna()].reset_index(drop=True)
    write_outputs(kept)
    written_back = write_back(cleaned) if args.write_back else []
    write_report(cleaned, kept, geocoder, stopped, written_back)
    log.info("wrote %s (+ per-input files) and %s", COMBINED_PATH, REPORT_PATH)
    for path in written_back:
        log.info("filled coordinates in %s (original kept as %s.bak)", path.name, path.name)
    if stopped:
        log.warning("geocoding stopped early: %s", stopped)


if __name__ == "__main__":
    main()
