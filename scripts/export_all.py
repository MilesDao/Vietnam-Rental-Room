"""
scripts/export_all.py - Convert all interim JSONL datasets to CSV and JSON formats
"""

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.parse.export import export_records
interim_dir = BASE_DIR / "data" / "interim"

print(f"Scanning {interim_dir} for parsed JSONL files...")
jsonl_files = list(interim_dir.glob("parsed_*.jsonl"))

for jf in jsonl_files:
    records = []
    with open(jf, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
    
    prefix = jf.stem.replace("parsed_", "raw_")
    print(f"Exporting {len(records)} records from {jf.name} -> {prefix}.json & {prefix}.csv ...")
    export_records(records, interim_dir, prefix)
    export_records(records, BASE_DIR, prefix)

print("\n🎉 ALL DATASETS EXPORTED TO CSV & JSON SUCCESSFULLY!")
