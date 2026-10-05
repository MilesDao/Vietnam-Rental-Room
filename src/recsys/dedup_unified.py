"""Mark cross-platform duplicate rooms in the unified dataset.

    python -m src.recsys.dedup_unified     # ~1 min, O(n^2) within each district

Adds duplicate_of / n_duplicates (see sample_schema.mark_duplicates) and writes
data/unified_hanoi_rentals_dedup.csv; recommend.load() drops rows with duplicate_of set.
"""
import pandas as pd

from src.clean.sample_schema import mark_duplicates

SRC = "data/unified_hanoi_rentals_geofixed.csv"  # from python -m src.recsys.regeocode_fallback
OUT = "data/unified_hanoi_rentals_dedup.csv"


def main():
    d = pd.read_csv(SRC, low_memory=False)
    r = mark_duplicates(d, cross_platform=True)
    r.to_csv(OUT, index=False, encoding="utf-8-sig")
    n = r.duplicate_of.notna().sum()
    print(f"{len(d)} rows -> {len(d) - n} kept, {n} duplicates folded; wrote {OUT}")


if __name__ == "__main__":
    main()
