"""Crawl several groups in one run, each into its own ``data/<slug>/`` folder.

Each group gets isolated output (posts.jsonl / posts.csv / checkpoints.json /
validation_report.md) and its own log, so the ``max_posts`` cap, dedup and
restart all work per-group. Duplicate group URLs are crawled only once.

Usage::

    python -m src.multi --config config.yaml --max-posts 2000 \
        --groups https://www.facebook.com/groups/AAA \
                 https://www.facebook.com/groups/BBB
"""

from __future__ import annotations

import argparse
import copy
import re
import sys
from pathlib import Path

from . import crawler, exporter


def slug_for(group_url: str) -> str:
    """Derive a filesystem-safe slug from a group URL (the id/vanity name)."""
    m = re.search(r"/groups/([^/?#]+)", group_url)
    slug = (m.group(1) if m else "group").strip("/")
    return re.sub(r"[^A-Za-z0-9_.-]", "_", slug) or "group"


def build_group_cfg(base_cfg: dict, group_url: str, base_dir: Path) -> dict:
    """Clone the base config for one group with per-group output paths."""
    cfg = copy.deepcopy(base_cfg)
    cfg["group_url"] = group_url
    slug = slug_for(group_url)
    d = base_dir / "data" / slug
    cfg["paths"] = {
        "posts_jsonl": str(d / "posts.jsonl"),
        "posts_csv": str(d / "posts.csv"),
        "checkpoint": str(d / "checkpoints.json"),
        "validation_report": str(d / "validation_report.md"),
        "log": str(base_dir / "logs" / f"{slug}.log"),
        "dom_sample": str(d / "dom_sample.html"),
    }
    return cfg


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Crawl multiple Facebook groups (read-only).")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--groups", nargs="+", required=True, help="Group URLs")
    ap.add_argument("--max-posts", type=int, default=None, help="Per-group cap")
    args = ap.parse_args(argv)

    base_cfg = crawler.load_config(args.config)
    base_dir = Path(args.config).resolve().parent
    if args.max_posts is not None:
        base_cfg["max_posts"] = args.max_posts

    # De-duplicate group URLs, preserving order.
    seen: set[str] = set()
    groups: list[str] = []
    for g in args.groups:
        if g not in seen:
            seen.add(g)
            groups.append(g)
    skipped = len(args.groups) - len(groups)
    if skipped:
        print(f"[multi] ignored {skipped} duplicate group URL(s)", file=sys.stderr)

    results = []
    for i, g in enumerate(groups, start=1):
        cfg = build_group_cfg(base_cfg, g, base_dir)
        Path(cfg["paths"]["posts_jsonl"]).parent.mkdir(parents=True, exist_ok=True)
        print(f"\n[multi] ({i}/{len(groups)}) crawling {g} "
              f"(slug={slug_for(g)}, cap={cfg['max_posts']})", file=sys.stderr)
        try:
            stop = crawler.crawl(cfg, inspect=False)
        except Exception as exc:  # never let one group kill the rest
            print(f"[multi] group {slug_for(g)} errored: {exc}", file=sys.stderr)
            stop = "error"
        rows = exporter.export_csv(cfg["paths"]["posts_jsonl"], cfg["paths"]["posts_csv"])
        stats = exporter.generate_validation_report(
            cfg["paths"]["posts_jsonl"], cfg["paths"]["validation_report"], g
        )
        results.append((slug_for(g), stop, rows, stats))

    print("\n===== MULTI-CRAWL SUMMARY =====", file=sys.stderr)
    for slug, stop, rows, stats in results:
        print(f"  {slug}: stop={stop} total={stats['total']} "
              f"permalink={stats['with_permalink']} images={stats['with_images']} "
              f"reactions={stats['with_reactions']} dupes={stats['duplicates']}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
