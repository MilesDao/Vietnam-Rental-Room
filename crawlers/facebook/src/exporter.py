"""Storage layer: incremental JSONL append, checkpointing, CSV export, report.

No Facebook DOM knowledge here — this module only reads/writes structured data.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from . import utils

CSV_COLUMNS = [
    "post_id",
    "post_url",
    "group_url",
    "timestamp_text",
    "timestamp",
    "text",
    "reaction_count",
    "comment_count",
    "share_count",
    "image_urls",
    "video_urls",
    "crawl_time",
]


def append_posts(jsonl_path: str | Path, records: Iterable[dict]) -> int:
    """Append records to the JSONL file, flushing and fsyncing to disk.

    Returns the number of records written. Each record is written as one
    UTF-8 line with ``ensure_ascii=False`` so Vietnamese/emoji survive.
    """
    p = Path(jsonl_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
        fh.flush()
        os.fsync(fh.fileno())
    return count


def read_checkpoint(path: str | Path) -> dict:
    """Read the checkpoint file, or return an empty dict if absent/corrupt."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_checkpoint(
    path: str | Path,
    *,
    group_url: str,
    unique_posts: int,
    last_post_url: str | None,
    scroll_attempts: int,
    stop_reason: str | None = None,
) -> None:
    """Atomically write the checkpoint file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "group_url": group_url,
        "unique_posts": unique_posts,
        "last_post_url": last_post_url,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "scroll_attempts": scroll_attempts,
    }
    if stop_reason:
        payload["stop_reason"] = stop_reason
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def export_csv(jsonl_path: str | Path, csv_path: str | Path) -> int:
    """Convert posts.jsonl to a UTF-8 CSV. Media arrays become JSON strings.

    Returns the number of rows written.
    """
    records = utils.load_jsonl(jsonl_path)
    p = Path(csv_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = {col: record.get(col) for col in CSV_COLUMNS}
            row["image_urls"] = json.dumps(record.get("image_urls") or [], ensure_ascii=False)
            row["video_urls"] = json.dumps(record.get("video_urls") or [], ensure_ascii=False)
            writer.writerow(row)
    return len(records)


def generate_validation_report(
    jsonl_path: str | Path,
    report_path: str | Path,
    group_url: str,
) -> dict:
    """Compute per-field coverage stats and write a Markdown validation report.

    Returns the stats dict as well, for logging/testing.
    """
    records = utils.load_jsonl(jsonl_path)
    total = len(records)

    def count_if(pred) -> int:
        return sum(1 for r in records if pred(r))

    keys = [utils.post_identity_key(r) for r in records]
    duplicates = len(keys) - len(set(keys))

    stats = {
        "total": total,
        "with_permalink": count_if(lambda r: bool(r.get("post_url"))),
        "with_post_id": count_if(lambda r: bool(r.get("post_id"))),
        "with_text": count_if(lambda r: bool(r.get("text"))),
        "with_reactions": count_if(lambda r: r.get("reaction_count") is not None),
        "with_comments": count_if(lambda r: r.get("comment_count") is not None),
        "with_shares": count_if(lambda r: r.get("share_count") is not None),
        "with_images": count_if(lambda r: bool(r.get("image_urls"))),
        "with_videos": count_if(lambda r: bool(r.get("video_urls"))),
        "duplicates": duplicates,
        # A record with neither permalink nor text is an extraction failure.
        "extraction_failures": count_if(
            lambda r: not r.get("post_url") and not r.get("text")
        ),
    }

    lines = [
        "# Validation Report",
        "",
        f"- Group URL: `{group_url}`",
        f"- Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Coverage",
        "",
        f"- Posts collected: **{stats['total']}**",
        f"- With valid permalink: **{stats['with_permalink']}**",
        f"- With parsed post_id: **{stats['with_post_id']}**",
        f"- With text: **{stats['with_text']}**",
        f"- With reaction count: **{stats['with_reactions']}**",
        f"- With comment count: **{stats['with_comments']}**",
        f"- With share count: **{stats['with_shares']}**",
        f"- Containing images: **{stats['with_images']}**",
        f"- Containing videos: **{stats['with_videos']}**",
        f"- Duplicates detected: **{stats['duplicates']}**",
        f"- Extraction failures (no url and no text): **{stats['extraction_failures']}**",
        "",
        "## Manual spot-check",
        "",
        "Open each permalink below in your logged-in browser and confirm the",
        "extracted text / counts match what Facebook shows. Fill in PASS/FAIL.",
        "",
        "| # | post_url | text ok? | reactions ok? | comments ok? |",
        "|---|----------|----------|---------------|--------------|",
    ]
    for i, r in enumerate(records[:5], start=1):
        url = r.get("post_url") or "(none)"
        lines.append(f"| {i} | {url} |  |  |  |")
    lines.append("")

    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text("\n".join(lines), encoding="utf-8")
    return stats
