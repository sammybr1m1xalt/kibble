#!/usr/bin/env python3
"""
metric-diff — compare two kibble snapshots and show what changed.

Usage:
    python scripts/metric-diff.py <snapshot1> <snapshot2>
    python scripts/metric-diff.py out/snapshots/kibble-snapshot-20260906T035034Z.json out/snapshots/kibble-snapshot-20260906T041227Z.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

NUMERIC_KEYS = (
    "export_lines",
    "job_count",
    "jobs_with_at_least_one_attest",
    "jobs_with_no_verdict",
    "verdict_coverage_pct",
    "deliver_result_count",
    "canned_template_hits",
    "canned_template_rate_pct",
    "jobs_with_claims",
    "multi_claim_job_count",
    "multi_claim_rate_pct",
    "jobs_with_delivery",
    "jobs_with_no_delivery",
    "no_delivery_rate_pct",
    "attest_count",
    "attest_senders",
    "senders_with_low_diversity_reason_reuse",
    "senders_reusing_one_reason",
)


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def diff_stats(a: dict, b: dict) -> list[tuple[str, float, float, float]]:
    """Return list of (key, a_val, b_val, delta)."""
    results = []
    for key in NUMERIC_KEYS:
        av = a.get(key, 0)
        bv = b.get(key, 0)
        delta = bv - av
        results.append((key, av, bv, delta))
    return results


def sender_key(sender: dict) -> str:
    return sender.get("sender", "")


def diff_sender_table(a: list, b: list) -> dict:
    """Compare sender reuse tables. Returns {sender: (a_count, b_count, delta)}."""
    a_map = {sender_key(s): s for s in a}
    b_map = {sender_key(s): s for s in b}
    all_senders = sorted(set(a_map) | set(b_map))
    result = {}
    for s in all_senders:
        ac = a_map[s]["total_attests"] if s in a_map else 0
        bc = b_map[s]["total_attests"] if s in b_map else 0
        result[s] = (ac, bc, bc - ac)
    return result


def fmt_delta(key: str, av: float, bv: float, delta: float) -> str:
    if isinstance(av, float) or isinstance(bv, float):
        return f"{delta:+.2f}"
    return f"{delta:+d}"


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python scripts/metric-diff.py",
        description="Compare two kibble snapshots",
    )
    parser.add_argument("file_a", type=str, help="first snapshot (older)")
    parser.add_argument("file_b", type=str, help="second snapshot (newer)")
    args = parser.parse_args(argv)

    path_a = Path(args.file_a)
    path_b = Path(args.file_b)
    if not path_a.exists():
        print(f"File not found: {path_a}")
        return 1
    if not path_b.exists():
        print(f"File not found: {path_b}")
        return 1

    a = load(path_a)
    b = load(path_b)
    stats_a = a.get("stats", {})
    stats_b = b.get("stats", {})

    print(f"Comparing:")
    print(f"  A: {path_a.name}  ({a.get('run_ts','')}  did={a.get('did','')[:30]}...)")
    print(f"  B: {path_b.name}  ({b.get('run_ts','')}  did={b.get('did','')[:30]}...)")
    print()

    print("Metric deltas:")
    print(f"  {'metric':<35} {'A':>10} {'B':>10} {'delta':>10}")
    print(f"  {'-'*35} {'-'*10} {'-'*10} {'-'*10}")
    for key, av, bv, delta in diff_stats(stats_a, stats_b):
        print(f"  {key:<35} {av:>10} {bv:>10} {fmt_delta(key, av, bv, delta):>10}")
    print()

    # Sender table diff
    senders_a = stats_a.get("sender_reuse_table", [])
    senders_b = stats_b.get("sender_reuse_table", [])
    if senders_a or senders_b:
        print("Sender table deltas (by total_attests):")
        sender_diff = diff_sender_table(senders_a, senders_b)
        for sender, (ac, bc, delta) in sorted(sender_diff.items()):
            short = sender[:40]
            flag = ""
            if delta > 0:
                flag = " (+new)"
            elif delta < 0:
                flag = " (-gone)"
            print(f"  {short:<40} {ac:>5} → {bc:>5} {delta:+d}{flag}")
    print()

    # Verify both snapshots
    print("Verification:")
    from kibble_verifier import verify_snapshot

    for label, snap in [("A", a), ("B", b)]:
        ok = verify_snapshot(
            snap.get("did", ""),
            snap.get("snapshot_hash", ""),
            snap.get("signature", ""),
            snap.get("stats", {}),
        )
        print(f"  {label} ({snap.get('run_ts','')[:15]}): {'✓ VALID' if ok else '✗ INVALID'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
