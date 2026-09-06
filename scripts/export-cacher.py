#!/usr/bin/env python3
"""
export-cacher — cache the /r/kibble/export JSONL locally for fast repeated reads.

Usage:
    python scripts/export-cacher.py            # fetch + cache (overwrites)
    python scripts/export-cacher.py --read     # read from cache, no fetch
    python scripts/export-cacher.py --stale    # fetch only if cache > --max-age
    python scripts/export-cacher.py --stats    # show cache stats

The cache is out/export-cache.jsonl. Each run updates a sidecar
out/export-cache.meta.json with fetch timestamp and line count.

The verifier can be pointed at the cache via a future --cache flag
(instead of fetching live every time). For now, this script is the
cache maintenance tool.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_DIR / "out"
CACHE_PATH = OUT_DIR / "export-cache.jsonl"
META_PATH = OUT_DIR / "export-cache.meta.json"
KIBBLE_EXPORT = "https://technocore.chat/r/kibble/export"


def fetch_export(timeout_s: int = 30) -> tuple[str, int]:
    """Fetch the export and return (raw_text, line_count)."""
    req = urllib.request.Request(KIBBLE_EXPORT)
    raw = urllib.request.urlopen(req, timeout=timeout_s).read().decode("utf-8")
    count = len([l for l in raw.splitlines() if l.strip()])
    return raw, count


def write_cache(raw: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(raw)
    meta = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fetch_timestamp": int(time.time()),
        "line_count": len([l for l in raw.splitlines() if l.strip()]),
        "size_bytes": len(raw.encode("utf-8")),
    }
    META_PATH.write_text(json.dumps(meta, indent=2) + "\n")


def read_cache_stats() -> dict | None:
    if not CACHE_PATH.exists():
        return None
    if not META_PATH.exists():
        return None
    meta = json.loads(META_PATH.read_text())
    size = CACHE_PATH.stat().st_size
    age_s = time.time() - meta["fetch_timestamp"]
    return {
        "fetched_at": meta["fetched_at"],
        "age_seconds": int(age_s),
        "age_human": format_age(age_s),
        "line_count": meta["line_count"],
        "size_bytes": size,
        "size_human": format_size(size),
    }


def format_age(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds//60}m ago"
    if seconds < 86400:
        return f"{seconds//3600}h ago"
    return f"{seconds//86400}d ago"


def format_size(bytes_: int) -> str:
    if bytes_ < 1024:
        return f"{bytes_} B"
    if bytes_ < 1024 * 1024:
        return f"{bytes_ / 1024:.1f} KB"
    return f"{bytes_ / (1024*1024):.1f} MB"


def cmd_fetch(args):
    max_age = args.max_age
    if args.stale:
        stats = read_cache_stats()
        if stats and stats["age_seconds"] < max_age:
            print(f"Cache is fresh ({stats['age_human']}). Skipping fetch.")
            print(f"  Lines: {stats['line_count']}, Size: {stats['size_human']}")
            return
        print(f"Cache stale ({stats['age_human'] if stats else 'never fetched'}). Fetching...")
    else:
        print("Fetching /r/kibble/export ...")

    t0 = time.time()
    raw, count = fetch_export()
    write_cache(raw)
    elapsed = time.time() - t0
    size = format_size(len(raw.encode("utf-8")))
    print(f"  Fetched {count} lines ({size}) in {elapsed:.2f}s")
    print(f"  Cached to {CACHE_PATH}")
    print(f"  Meta: {META_PATH}")


def cmd_read(args):
    if not CACHE_PATH.exists():
        print("No cache found. Run without --read first.")
        return 1
    stats = read_cache_stats()
    if not stats:
        print("Cache exists but no meta. Re-fetching metadata...")
        return 1
    print(f"Export cache:")
    print(f"  Path:       {CACHE_PATH}")
    print(f"  Fetched:    {stats['fetched_at']}")
    print(f"  Age:        {stats['age_human']}")
    print(f"  Lines:      {stats['line_count']}")
    print(f"  Size:       {stats['size_human']}")
    print()
    # Count line types
    from collections import Counter
    kinds = Counter()
    for line in CACHE_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        for prefix in ("JOB ", "CLAIM ", "DELIVER ", "RESULT ", "ATTEST "):
            if line.startswith(prefix):
                kinds[prefix.strip()] += 1
                break
    print(f"  Line types:")
    for k, v in sorted(kinds.items()):
        print(f"    {k}: {v}")
    return 0


def cmd_stats(args):
    stats = read_cache_stats()
    if not stats:
        print("No cache found. Run 'python scripts/export-cacher.py' first.")
        return 1
    print(json.dumps(stats, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python scripts/export-cacher.py",
        description="Cache /r/kibble/export locally for fast repeated reads",
    )
    parser.add_argument("--read", action="store_true", help="read cache stats, no fetch")
    parser.add_argument("--stale", action="store_true",
                        help="fetch only if cache older than --max-age (default: 3600s)")
    parser.add_argument("--max-age", type=int, default=3600,
                        help="max cache age in seconds before refetch (default: 3600 = 1h)")
    parser.add_argument("--stats", action="store_true", help="show cache stats as JSON")
    args = parser.parse_args(argv)

    if args.stats:
        return cmd_stats(args)
    elif args.read:
        return cmd_read(args)
    else:
        return cmd_fetch(args)


if __name__ == "__main__":
    sys.exit(main())
