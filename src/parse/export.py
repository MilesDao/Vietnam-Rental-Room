"""
src/parse/export.py - Export Parsed Listings to CSV and JSON formats

Handles:
- Pretty-printed JSON and JSON Array
- Flat tabular CSV with UTF-8 BOM for Microsoft Excel compatibility
"""

import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def export_records(
    records: List[Dict[str, Any]],
    output_base_path: Path,
    file_prefix: str,
) -> Dict[str, Path]:
    """
    Export a list of dictionary records to both JSON and CSV files.
    
    Args:
        records: List of canonical listing dictionaries
        output_base_path: Destination directory (e.g. data/interim/ or root)
        file_prefix: Base name without extension (e.g. 'raw_phongtro123_hanoi' or 'raw_alonhadat_hanoi')
        
    Returns:
        Dict mapping format name to output Path ('json': path, 'csv': path)
    """
    output_base_path.mkdir(parents=True, exist_ok=True)
    json_path = output_base_path / f"{file_prefix}.json"
    csv_path = output_base_path / f"{file_prefix}.csv"

    if not records:
        logger.warning(f"No records provided to export for {file_prefix}")
        # Create empty files
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        with open(csv_path, "w", encoding="utf-8-sig") as f:
            pass
        return {"json": json_path, "csv": csv_path}

    # 1. Export JSON (Formatted Array)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    logger.info(f"✅ Exported JSON: {json_path} ({len(records)} records)")

    # 2. Collect all unique keys across all records for CSV header
    all_keys = []
    for r in records:
        for k in r.keys():
            if k not in all_keys:
                all_keys.append(k)

    # 3. Export CSV (with UTF-8 SIG for Excel Vietnamese character support)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for r in records:
            row = {}
            for k in all_keys:
                val = r.get(k)
                if isinstance(val, (list, dict)):
                    row[k] = json.dumps(val, ensure_ascii=False)
                elif val is None:
                    row[k] = ""
                else:
                    row[k] = val
            writer.writerow(row)
    logger.info(f"✅ Exported CSV: {csv_path} ({len(records)} records)")

    return {"json": json_path, "csv": csv_path}
