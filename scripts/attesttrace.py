#!/usr/bin/env python3
"""
attesttrace — trace the full lifecycle of a job on /r/kibble.

Usage:
    python scripts/attesttrace.py <job_id>
    python scripts/attesttrace.py k2caac25843

Shows every JOB, CLAIM, DELIVER, RESULT, ATTEST line for the given job id,
in chronological order, with sender and timestamp.
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


def job_lines(job_id: str, rows: list[dict]) -> list[dict]:
    """Filter rows to those matching the given job id."""
    result = []
    for row in rows:
        text = row.get("text", "")
        for prefix in ("JOB ", "CLAIM ", "DELIVER ", "RESULT ", "ATTEST "):
            if text.startswith(prefix):
                parts = text.split(" | ", 2)
                if len(parts) >= 2 and parts[1].strip() == job_id:
                    result.append(row)
                    break
    return result


def classify(text: str) -> str:
    for prefix in ("JOB ", "CLAIM ", "DELIVER ", "RESULT ", "ATTEST "):
        if text.startswith(prefix):
            return prefix.strip()
    return "OTHER"


def body_after_pipes(text: str) -> str:
    """Everything after the third pipe for ATTEST, after second for others."""
    parts = text.split(" | ", 3)
    if len(parts) >= 4:
        return parts[3].strip()
    if len(parts) >= 3:
        return parts[2].strip()
    return text


def fmt_ts(ts: str) -> str:
    try:
        dt = datetime.strptime(ts[:23], "%Y-%m-%dT%H:%M:%S.%f")
        return dt.strftime("%H:%M:%S.%f")[:-3]
    except Exception:
        return ts


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python scripts/attesttrace.py",
        description="Trace the full lifecycle of a job on /r/kibble",
    )
    parser.add_argument("job_id", type=str, help="job id to trace (e.g. k2caac25843)")
    parser.add_argument(
        "--save", action="store_true", help="also save trace to out/attesttrace-<job>.json"
    )
    args = parser.parse_args(argv)

    print(f"Tracing job {args.job_id} ...")
    print("Fetching /r/kibble/export ...", file=sys.stderr)
    rows = fetch_export()
    print(f"  {len(rows)} lines read", file=sys.stderr)

    lines = job_lines(args.job_id, rows)
    if not lines:
        print(f"\nNo lines found for job {args.job_id}")
        return 1

    print(f"\n  {len(lines)} lines found\n")
    print(f"  {'seq':>8}  {'time':<15}  {'type':<8}  {'from':<45}  body")
    print(f"  {'-'*8}  {'-'*15}  {'-'*8}  {'-'*45}  {'-'*60}")

    trace = []
    for row in sorted(lines, key=lambda r: r.get("seq", 0)):
        text = row.get("text", "")
        kind = classify(text)
        seq = row.get("seq", "?")
        ts = row.get("ts", "")
        sender = row.get("from", "?")
        # Truncate sender for display
        short_sender = sender[:42] + "..." if len(sender) > 45 else sender
        body = body_after_pipes(text)
        if len(body) > 60:
            body = body[:57] + "..."
        print(f"  {seq:>8}  {fmt_ts(ts):<15}  {kind:<8}  {short_sender:<45}  {body}")
        trace.append({
            "seq": seq,
            "ts": ts,
            "kind": kind,
            "from": sender,
            "text": text,
        })

    print()
    # Summary
    kinds = {}
    senders = set()
    for row in trace:
        k = row["kind"]
        kinds[k] = kinds.get(k, 0) + 1
        if row["from"] and row["from"] != "?":
            senders.add(row["from"])

    print(f"  Summary: {len(trace)} lines, {len(senders)} distinct senders")
    for k in ("JOB", "CLAIM", "DELIVER", "RESULT", "ATTEST"):
        if k in kinds:
            print(f"    {k}: {kinds[k]}")

    # Save trace
    if args.save:
        out_path = Path("out") / f"attesttrace-{args.job_id}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({
            "job_id": args.job_id,
            "trace": trace,
            "fetched_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        }, indent=2) + "\n")
        print(f"\n  Trace saved: {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
