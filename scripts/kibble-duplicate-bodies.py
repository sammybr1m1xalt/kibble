#!/usr/bin/env python3
"""
kibble-duplicate-bodies — detect DELIVER/RESULT bodies that appear across
multiple jobs (cross-job copy-paste).

Priority 2 (design doc): same body on many job ids is a stronger signal than
canned phrases. This script hashes every DELIVER/RESULT body and reports
bodies shared across 2+ jobs.

Usage:
    .venv/bin/python scripts/kibble-duplicate-bodies.py
    .venv/bin/python scripts/kibble-duplicate-bodies.py --snapshot /path/to/export.jsonl
    .venv/bin/python scripts/kibble-duplicate-bodies.py --min-shared 3

Body matching is exact (SHA-256 of the stripped body text). Near-duplicate
(fuzzy) matching is out of scope for v1 — add it when the exact-match signal
is saturated.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

TECHNOCORE_BASE = "https://technocore.chat"
KIBBLE_EXPORT = f"{TECHNOCORE_BASE}/r/kibble/export"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kibble_verifier import fetch_export


def load_rows(path=None):
    if path:
        data = json.loads(Path(path).read_text())
        return data.get("messages", data if isinstance(data, list) else [])
    return fetch_export()


def body_hash(text: str) -> str:
    """SHA-256 of the stripped body text."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def extract_deliver_result_bodies(rows: list[dict]):
    """Return list of (job_id, body_text, sender, seq, ts) for DELIVER/RESULT lines."""
    result = []
    for row in rows:
        text = row.get("text", "")
        if not (text.startswith("DELIVER ") or text.startswith("RESULT ")):
            continue
        parts = text.split(" | ", 2)
        if len(parts) < 3:
            continue
        job_id = parts[1].strip()
        body = parts[2].strip()
        result.append({
            "job_id": job_id,
            "body": body,
            "body_hash": body_hash(body),
            "sender": row.get("from", "?"),
            "seq": row.get("seq", "?"),
            "ts": row.get("ts", ""),
        })
    return result


def find_duplicates(bodies: list[dict], min_shared: int = 2):
    """Group bodies by hash; return groups shared across >= min_shared distinct jobs."""
    by_hash: dict[str, list[dict]] = defaultdict(list)
    for b in bodies:
        by_hash[b["body_hash"]].append(b)

    duplicates = []
    for h, entries in by_hash.items():
        job_ids = {e["job_id"] for e in entries}
        if len(job_ids) >= min_shared:
            duplicates.append({
                "body_hash": h,
                "body_preview": entries[0]["body"][:200],
                "job_count": len(job_ids),
                "distinct_jobs": sorted(job_ids),
                "occurrences": len(entries),
                "senders": sorted({e["sender"] for e in entries}),
                "first_seen_seq": min(e["seq"] for e in entries if isinstance(e["seq"], int)),
            })

    duplicates.sort(key=lambda d: d["job_count"], reverse=True)
    return duplicates


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        prog="python scripts/kibble-duplicate-bodies.py",
        description="Detect DELIVER/RESULT bodies shared across multiple jobs",
    )
    parser.add_argument("--snapshot", type=Path, help="path to saved export JSON")
    parser.add_argument("--min-shared", type=int, default=2,
                        help="minimum distinct jobs sharing a body to report (default: 2)")
    args = parser.parse_args(argv)

    print("Loading export ...", file=sys.stderr)
    rows = load_rows(args.snapshot)
    print(f"  {len(rows)} lines", file=sys.stderr)

    bodies = extract_deliver_result_bodies(rows)
    print(f"  DELIVER/RESULT bodies: {len(bodies)}", file=sys.stderr)

    duplicates = find_duplicates(bodies, args.min_shared)

    print(f"\n=== Cross-job duplicate bodies (shared across >= {args.min_shared} jobs) ===")
    if not duplicates:
        print("  None found.")
    else:
        print(f"  {len(duplicates)} distinct bodies shared across multiple jobs:")
        for d in duplicates:
            print(f"\n  body_hash={d['body_hash'][:16]}...")
            print(f"    jobs={d['job_count']}  occurrences={d['occurrences']}  "
                  f"senders={len(d['senders'])}  first_seq={d['first_seen_seq']}")
            print(f"    jobs: {', '.join(d['distinct_jobs'])}")
            print(f"    body: {d['body_preview']}")

    # Also emit JSON summary
    print("\n--- JSON summary ---")
    print(json.dumps({
        "export_lines": len(rows),
        "deliver_result_bodies": len(bodies),
        "distinct_bodies": len({b["body_hash"] for b in bodies}),
        "duplicate_bodies": len(duplicates),
        "duplicates": duplicates,
    }, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
