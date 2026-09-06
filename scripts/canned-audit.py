#!/usr/bin/env python3
"""
canned-audit — show the actual DELIVER/RESULT bodies that matched canned phrases.

Usage:
    python scripts/canned-audit.py                    # audit latest snapshot
    python scripts/canned-audit.py --file <snap>      # audit specific snapshot
    python scripts/canned-audit.py --limit 5          # show first 5 only
    python scripts/canned-audit.py --matched-only     # show only matched (not all)

For each DELIVER/RESULT line that matched a canned phrase, shows:
- The job id
- The body text (truncated)
- Which phrase(s) matched
- The sender (from line)

This lets you eyeball whether the template detector is producing false positives.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

KIBBLE_EXPORT = "https://technocore.chat/r/kibble/export"


def fetch_export(timeout_s: int = 30) -> list[dict]:
    req = urllib.request.Request(KIBBLE_EXPORT)
    raw = urllib.request.urlopen(req, timeout=timeout_s).read().decode("utf-8")
    lines = raw.splitlines()
    rows: list[dict] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def load_snapshot(path: Path) -> dict:
    return json.loads(path.read_text())


def load_latest() -> dict | None:
    snaps = sorted(Path(__file__).resolve().parent.parent.joinpath("out", "snapshots").glob("kibble-snapshot-*.json"))
    if not snaps:
        return None
    return load_snapshot(snaps[-1])


def extract_canned_hits(rows: list[dict], canned_phrases: list[str]) -> list[dict]:
    """Extract DELIVER/RESULT lines that matched canned phrases."""
    hits: list[dict] = []
    for row in rows:
        text = row.get("text", "")
        for prefix in ("DELIVER ", "RESULT "):
            if text.startswith(prefix):
                parts = text.split(" | ", 2)
                if len(parts) >= 3:
                    body = parts[2].strip()
                    low = body.lower()
                    matched = [p for p in canned_phrases if p in low]
                    if matched:
                        job_id = parts[1].strip() if len(parts) >= 2 else "?"
                        hits.append({
                            "seq": row.get("seq", "?"),
                            "ts": row.get("ts", ""),
                            "job_id": job_id,
                            "sender": row.get("from", "?"),
                            "body": body,
                            "matched_phrases": matched,
                        })
                break
    return hits


def truncate(s: str, max_len: int = 120) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python scripts/canned-audit.py",
        description="Show DELIVER/RESULT bodies that matched canned phrases",
    )
    parser.add_argument("--file", type=str, help="specific snapshot file")
    parser.add_argument("--limit", type=int, default=0, help="max hits to show (0=all)")
    parser.add_argument("--matched-only", action="store_true",
                        help="show only matched bodies (default shows summary + hits)")
    parser.add_argument("--show-all", action="store_true",
                        help="also show non-matching bodies for comparison")
    args = parser.parse_args(argv)

    # Load snapshot or fetch live
    if args.file:
        snap = load_snapshot(Path(args.file))
        rows = []  # We only have stats in snapshot, not raw rows
        canned = snap.get("stats", {}).get("canned_phrases", [])
        print(f"Snapshot: {Path(args.file).name}")
        print(f"  Canned phrases: {canned}")
        print(f"  Template hits in snapshot: {snap.get('stats',{}).get('canned_template_hits','?')}")
        print(f"  Template total in snapshot: {snap.get('stats',{}).get('deliver_result_count','?')}")
        print()
        print("Note: snapshot only contains aggregate stats. To see actual bodies,")
        print("re-run without --file to fetch live export, or pass --fetch.")
        return 0

    # Live fetch
    print("Fetching /r/kibble/export ...")
    rows = fetch_export()
    print(f"  {len(rows)} lines read")
    print()

    canned = [
        "completed work on",
        "this concept involves key principles",
        "based on the available information",
        "based on available information",
        "sign-off promising useful output for the ecosystem",
    ]

    hits = extract_canned_hits(rows, canned)
    total_delivers = sum(1 for r in rows if r.get("text","").startswith(("DELIVER ","RESULT ")))
    print(f"Total DELIVER/RESULT lines: {total_delivers}")
    print(f"Canned phrase hits: {len(hits)} ({len(hits)/total_delivers*100:.1f}% of delivers)")
    print(f"Canned phrases: {canned}")
    print()

    if hits:
        print(f"▼ MATCHED BODIES ({len(hits)}):")
        print()
        for i, h in enumerate(hits[: args.limit or len(hits)]):
            print(f"  [{i+1}] seq={h['seq']}  job={h['job_id']}  {h['ts'][:16]}")
            print(f"      sender: {h['sender'][:40]}")
            print(f"      body:   {truncate(h['body'], 100)}")
            print(f"      matched: {', '.join(h['matched_phrases'])}")
            print()
    else:
        print("✓ No canned phrase hits found in this export")

    return 0


if __name__ == "__main__":
    sys.exit(main())
