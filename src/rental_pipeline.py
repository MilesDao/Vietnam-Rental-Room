"""Resumable batch orchestration for DeepSeek-backed rental extraction."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .deepseek_rental_parser import (
    PROMPT_VERSION,
    DeepSeekRentalParser,
    cache_key,
)
from .rental_schema import OUTPUT_COLUMNS, build_rows, validate_response, write_output_csv


def load_environment(path: Path = Path(".env")) -> None:
    """Load local configuration without replacing process environment values."""
    load_dotenv(dotenv_path=path, override=False)


def require_api_key() -> str:
    """Return the configured DeepSeek key or fail before any processing starts."""
    value = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not value:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is missing; set it in .env or the process environment"
        )
    return value


@dataclass(frozen=True)
class PipelineSettings:
    input_path: Path
    output_path: Path
    cache_path: Path
    audit_path: Path
    report_path: Path
    model: str
    concurrency: int = 4
    limit: int | None = None
    force: bool = False
    cache_only: bool = False


@dataclass(frozen=True)
class PipelineSummary:
    source_posts: int
    api_requests: int
    cache_hits: int
    accepted_posts: int
    accepted_rows: int
    skipped_posts: int
    skipped_by_classification: dict[str, int]
    failed_posts: int
    multi_row_posts: int
    retries: int


def read_sources(path: Path, limit: int | None = None) -> list[dict[str, str]]:
    """Read Facebook source rows with a small required-field contract."""
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = set(reader.fieldnames or [])
        required = {"post_id", "post_url", "text", "image_urls", "crawl_time"}
        missing = sorted(required - fields)
        if missing:
            raise ValueError(f"Input CSV is missing required columns: {', '.join(missing)}")
        rows: list[dict[str, str]] = []
        for row in reader:
            rows.append(dict(row))
            if limit is not None and len(rows) >= limit:
                break
    return rows


def load_cache(path: Path) -> dict[str, dict[str, Any]]:
    """Load the latest valid append-only record for each cache key."""
    records: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            key = record.get("cache_key") if isinstance(record, dict) else None
            if isinstance(key, str) and key:
                records[key] = record
    return records


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    """Append and durably flush one JSON record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _complete_cache_entry(record: dict[str, Any] | None) -> bool:
    return bool(
        record
        and record.get("error") is None
        and isinstance(record.get("payload"), dict)
    )


def _source_identity(source: dict[str, str], key: str) -> str:
    return source.get("post_id") or source.get("post_url") or f"hash:{key[:16]}"


async def run_pipeline(
    settings: PipelineSettings,
    parser: DeepSeekRentalParser,
) -> PipelineSummary:
    """Extract uncached sources, then deterministically rebuild all artifacts."""
    if settings.concurrency < 1:
        raise ValueError("concurrency must be positive")
    sources = read_sources(settings.input_path, settings.limit)
    prior_cache = load_cache(settings.cache_path)
    current_cache = dict(prior_cache)
    source_keys = [(source, cache_key(source, settings.model)) for source in sources]
    first_source_by_key: dict[str, dict[str, str]] = {}
    for source, key in source_keys:
        first_source_by_key.setdefault(key, source)

    if settings.cache_only:
        cached_keys = {
            key for key in first_source_by_key if prior_cache.get(key) is not None
        }
        keys_to_request: list[str] = []
    else:
        cached_keys = {
            key
            for key in first_source_by_key
            if not settings.force and _complete_cache_entry(prior_cache.get(key))
        }
        keys_to_request = [
            key for key in first_source_by_key if key not in cached_keys
        ]
    semaphore = asyncio.Semaphore(settings.concurrency)

    async def process(key: str) -> tuple[str, dict[str, Any]]:
        source = first_source_by_key[key]
        async with semaphore:
            outcome = await parser.extract(source)
        record = {
            "cache_key": key,
            "prompt_version": PROMPT_VERSION,
            "model": settings.model,
            "source_identity": _source_identity(source, key),
            "attempts": outcome.attempts,
            "payload": outcome.payload,
            "raw_content": outcome.raw_content,
            "error": outcome.error,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        append_jsonl(settings.cache_path, record)
        return key, record

    requested = await asyncio.gather(*(process(key) for key in keys_to_request))
    for key, record in requested:
        current_cache[key] = record

    all_rows: list[dict[str, Any]] = []
    audit_records: list[dict[str, Any]] = []
    skipped_by: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()
    accepted_posts = skipped_posts = failed_posts = multi_row_posts = 0

    for source, key in source_keys:
        record = current_cache.get(key) or {}
        cache_status = "hit" if key in cached_keys else "requested"
        produced_rows: list[dict[str, Any]] = []
        classification = "failed"
        skip_reason: str | None = None
        issues: list[dict[str, Any]] = []

        if _complete_cache_entry(record):
            validation = validate_response(record["payload"], source.get("text", ""))
            classification = validation.classification
            skip_reason = validation.skip_reason
            issues = [asdict(issue) for issue in validation.issues]
            issue_counts.update(issue.code for issue in validation.issues)
            if classification == "rental_offer":
                produced_rows = build_rows(source, validation.listings)
                if produced_rows:
                    accepted_posts += 1
                    if len(produced_rows) > 1:
                        multi_row_posts += 1
                    all_rows.extend(produced_rows)
                else:
                    failed_posts += 1
                    issue_counts["rental_offer_without_valid_rows"] += 1
                    issues.append(
                        {
                            "code": "rental_offer_without_valid_rows",
                            "message": "Rental offer produced no locally valid rows",
                            "option_index": None,
                        }
                    )
            elif classification in {
                "room_seeking", "property_sale", "recruitment",
                "warning_or_review", "general_information", "unrelated",
            }:
                skipped_posts += 1
                skipped_by[classification] += 1
            else:
                failed_posts += 1
        else:
            failed_posts += 1
            issues.append(
                {
                    "code": "api_failure",
                    "message": record.get("error") or "Missing cache result",
                    "option_index": None,
                }
            )
            issue_counts["api_failure"] += 1

        audit_records.append(
            {
                "source_identity": _source_identity(source, key),
                "cache_key": key,
                "cache_status": cache_status,
                "classification": classification,
                "skip_reason": skip_reason,
                "attempts": record.get("attempts", 0),
                "error": record.get("error"),
                "validation_issues": issues,
                "listing_ids": [row["listing_id"] for row in produced_rows],
            }
        )

    # A duplicate source identity must not create duplicate output IDs.
    rows_by_id = {row["listing_id"]: row for row in all_rows}
    all_rows = list(rows_by_id.values())
    write_output_csv(settings.output_path, all_rows)
    _write_jsonl(settings.audit_path, audit_records)

    summary = PipelineSummary(
        source_posts=len(sources),
        api_requests=len(keys_to_request),
        cache_hits=sum(1 for _source, key in source_keys if key in cached_keys),
        accepted_posts=accepted_posts,
        accepted_rows=len(all_rows),
        skipped_posts=skipped_posts,
        skipped_by_classification=dict(sorted(skipped_by.items())),
        failed_posts=failed_posts,
        multi_row_posts=multi_row_posts,
        retries=sum(max(0, int(record.get("attempts", 1)) - 1) for _, record in requested),
    )
    write_validation_report(settings.report_path, summary, all_rows, issue_counts)
    return summary


def write_validation_report(
    path: Path,
    summary: PipelineSummary,
    rows: list[dict],
    issue_counts: Counter[str],
) -> None:
    """Write processing reconciliation and target-field coverage."""
    reconciled = (
        summary.source_posts
        == summary.accepted_posts + summary.skipped_posts + summary.failed_posts
    )
    total_rows = len(rows)
    lines = [
        "# Facebook Rental Extraction Report",
        "",
        "## Processing",
        "",
        f"- Source posts: **{summary.source_posts}**",
        f"- API requests: **{summary.api_requests}**",
        f"- Cache hits: **{summary.cache_hits}**",
        f"- Accepted source posts: **{summary.accepted_posts}**",
        f"- Accepted listing rows: **{summary.accepted_rows}**",
        f"- Skipped posts: **{summary.skipped_posts}**",
        f"- Failed posts: **{summary.failed_posts}**",
        f"- Posts producing multiple rows: **{summary.multi_row_posts}**",
        f"- Retries: **{summary.retries}**",
        f"- Reconciliation: **{'PASS' if reconciled else 'MISMATCH'}**",
        "",
        "## Skipped classifications",
        "",
    ]
    if summary.skipped_by_classification:
        lines.extend(
            f"- {name}: **{count}**"
            for name, count in sorted(summary.skipped_by_classification.items())
        )
    else:
        lines.append("- None")
    lines.extend(["", "## Validation issues", ""])
    if issue_counts:
        lines.extend(
            f"- {name}: **{count}**" for name, count in sorted(issue_counts.items())
        )
    else:
        lines.append("- None")
    lines.extend(["", "## Output field coverage", ""])
    for column in OUTPUT_COLUMNS:
        present = sum(
            1
            for row in rows
            if row.get(column) is not None and row.get(column) != ""
        )
        lines.append(f"- {column}: **{present}/{total_rows}**")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def _positive_float(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the standalone rental extraction CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/posts_combined.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/facebook_rentals_parsed.csv"))
    parser.add_argument("--cache", type=Path, default=Path("data/deepseek_rental_cache.jsonl"))
    parser.add_argument("--audit", type=Path, default=Path("data/facebook_rental_audit.jsonl"))
    parser.add_argument("--report", type=Path, default=Path("data/facebook_rental_validation_report.md"))
    parser.add_argument("--model", default=os.environ.get("DEEPSEEK_MODEL", "deepseek-flash"))
    parser.add_argument("--base-url", default=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    parser.add_argument("--concurrency", type=_positive_int, default=4)
    parser.add_argument("--max-retries", type=_positive_int, default=4)
    parser.add_argument("--timeout", type=_positive_float, default=60.0)
    parser.add_argument("--limit", type=_positive_int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Rebuild outputs from cached responses without making API requests",
    )
    return parser


async def async_main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI after validating secrets and arguments."""
    load_environment()
    args = build_arg_parser().parse_args(argv)
    api_key = require_api_key()

    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=args.base_url,
        timeout=args.timeout,
        max_retries=0,
    )
    extractor = DeepSeekRentalParser(
        client,
        model=args.model,
        max_retries=args.max_retries,
    )
    settings = PipelineSettings(
        input_path=args.input,
        output_path=args.output,
        cache_path=args.cache,
        audit_path=args.audit,
        report_path=args.report,
        model=args.model,
        concurrency=args.concurrency,
        limit=args.limit,
        force=args.force,
        cache_only=args.cache_only,
    )
    summary = await run_pipeline(settings, extractor)
    print(json.dumps(asdict(summary), ensure_ascii=False, sort_keys=True))
    return 0


def main() -> None:
    try:
        code = asyncio.run(async_main())
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
    except Exception as error:
        status = getattr(error, "status_code", None)
        if status in {400, 401, 403}:
            print(f"DeepSeek API rejected the request (HTTP {status}).", file=sys.stderr)
            raise SystemExit(2) from error
        raise
    raise SystemExit(code)


if __name__ == "__main__":
    main()
