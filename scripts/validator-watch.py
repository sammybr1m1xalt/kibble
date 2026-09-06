#!/usr/bin/env python3
"""
validator-watch — surface per-sender reason reuse as alerts.

Usage:
    python scripts/validator-watch.py                    # analyze latest snapshot
    python scripts/validator-watch.py --file <snap>      # analyze specific snapshot
    python scripts/validator-watch.py --watch            # show only alerts (one-reason, low-diversity)
    python scripts/validator-watch.py --delta <snapA> <snapB>  # what changed between two snapshots

Flags senders that:
- Reuse a single reason for 100% of their ATTESTs (likely bot)
- Have low reason diversity (<=3 distinct reasons across all their ATTESTs)
- Appeared or disappeared between two snapshots
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "out" / "snapshots"


def load_snapshot(path: Path) -> dict:
    return json.loads(path.read_text())


def load_latest() -> dict:
    snaps = sorted(SNAPSHOT_DIR.glob("kibble-snapshot-*.json"))
    if not snaps:
        return None
    return load_snapshot(snaps[-1])


def classify_senders(sender_table: list[dict], low_threshold: int = 3) -> dict:
    """Classify senders by their reason diversity.

    Returns dict with keys:
      - one_reason: list of senders reusing exactly 1 reason
      - low_diversity: list of senders with <= low_threshold distinct reasons
      - diverse: list of senders with > low_threshold distinct reasons
    """
    one_reason = []
    low_diversity = []
    diverse = []

    for s in sender_table:
        distinct = s.get("distinct_reasons", 0)
        total = s.get("total_attests", 0)
        max_same = s.get("max_single_reason_count", 0)
        ratio = s.get("max_reuse_ratio", 0)

        entry = {
            "sender": s.get("sender", ""),
            "total": total,
            "distinct": distinct,
            "max_single_reason_count": max_same,
            "max_reuse_ratio": ratio,
        }

        if distinct == 1:
            one_reason.append(entry)
        elif distinct <= low_threshold:
            low_diversity.append(entry)
        else:
            diverse.append(entry)

    return {
        "one_reason": one_reason,
        "low_diversity": low_diversity,
        "diverse": diverse,
    }


def print_sender(sender: dict, indent: str = "    ") -> None:
    print(
        f"{indent}sender:    {sender['sender'][:50]}"
        f"\n{indent}total:     {sender['total']}"
        f"\n{indent}distinct:  {sender['distinct']}"
        f"\n{indent}max_same:  {sender['max_single_reason_count']}"
        f"\n{indent}reuse_ratio: {sender['max_reuse_ratio']:.2%}"
    )


def cmd_watch(args):
    if args.file:
        snap = load_snapshot(Path(args.file))
    else:
        snap = load_latest()

    if snap is None:
        print("No snapshots found.")
        return

    stats = snap.get("stats", {})
    sender_table = stats.get("sender_reuse_table", [])
    classification = classify_senders(sender_table)

    print(f"Snapshot: {snap.get('run_ts','')}  did={snap.get('did','')[:40]}...")
    print(f"  Verdict coverage: {stats.get('verdict_coverage_pct','?')}%")
    print(f"  Template rate:    {stats.get('canned_template_rate_pct','?')}%")
    print(f"  ATTEST senders:   {stats.get('attest_senders','?')}")
    print()

    # One-reason senders (most suspicious)
    if classification["one_reason"]:
        print(f"▼ ONE-REASON SENDERS ({len(classification['one_reason'])}) — reuse same reason 100%:")
        for s in classification["one_reason"]:
            print(f"\n  [{s['total']} ATTESTs, 1 distinct reason, reuse 100%]")
            print_sender(s)
    else:
        print("✓ No one-reason senders")

    print()

    # Low-diversity senders
    if classification["low_diversity"]:
        print(f"▼ LOW-DIVERSITY SENDERS ({len(classification['low_diversity'])}) — ≤3 distinct reasons:")
        for s in classification["low_diversity"]:
            if s not in classification["one_reason"]:
                print(f"\n  [{s['total']} ATTESTs, {s['distinct']} distinct reasons, reuse {s['max_reuse_ratio']:.0%}]")
                print_sender(s)
    else:
        print("✓ No low-diversity senders")

    print()

    # Diverse (normal)
    if classification["diverse"]:
        print(f"✓ DIVERSE SENDERS ({len(classification['diverse'])}):")
        for s in sorted(classification["diverse"], key=lambda x: -x["total"])[:10]:
            print(f"    {s['sender'][:40]:<40} {s['total']:>4} ATTESTs, {s['distinct']:>3} reasons")
    print()


def cmd_delta(args):
    path_a = Path(args.file_a)
    path_b = Path(args.file_b)
    if not path_a.exists():
        print(f"File not found: {path_a}")
        return 1
    if not path_b.exists():
        print(f"File not found: {path_b}")
        return 1

    a = load_snapshot(path_a)
    b = load_snapshot(path_b)
    table_a = a.get("stats", {}).get("sender_reuse_table", [])
    table_b = b.get("stats", {}).get("sender_reuse_table", [])

    map_a = {s["sender"]: s for s in table_a}
    map_b = {s["sender"]: s for s in table_b}
    all_senders = sorted(set(map_a) | set(map_b))

    print(f"Sender changes between {path_a.name[:15]} and {path_b.name[:15]}:")
    print()

    new_senders = []
    gone_senders = []
    growth = []
    shrinkage = []

    for sender in all_senders:
        in_a = sender in map_a
        in_b = sender in map_b
        if in_b and not in_a:
            new_senders.append(map_b[sender])
        elif in_a and not in_b:
            gone_senders.append(map_a[sender])
        else:
            a_count = map_a[sender]["total_attests"]
            b_count = map_b[sender]["total_attests"]
            delta = b_count - a_count
            if delta > 0:
                growth.append((sender, a_count, b_count, delta))
            elif delta < 0:
                shrinkage.append((sender, a_count, b_count, delta))

    if new_senders:
        print(f"▼ NEW SENDERS ({len(new_senders)}):")
        for s in new_senders:
            print(f"    + {s['sender'][:45]}  ({s['total']} ATTESTs, {s['distinct']} reasons)")
    else:
        print("✓ No new senders")

    if gone_senders:
        print(f"\n▼ GONE SENDERS ({len(gone_senders)}):")
        for s in gone_senders:
            print(f"    - {s['sender'][:45]}  ({s['total']} ATTESTs, {s['distinct']} reasons)")
    else:
        print("✓ No gone senders")

    if growth:
        print(f"\n▼ GROWING ({len(growth)}):")
        for sender, ac, bc, delta in sorted(growth, key=lambda x: -x[3])[:10]:
            print(f"    {sender[:40]:<40} {ac:>4} → {bc:>4}  (+{delta})")

    if shrinkage:
        print(f"\n▼ SHRINKING ({len(shrinkage)}):")
        for sender, ac, bc, delta in sorted(shrinkage, key=lambda x: x[3])[:10]:
            print(f"    {sender[:40]:<40} {ac:>4} → {bc:>4}  ({delta})")

    if not new_senders and not gone_senders and not growth and not shrinkage:
        print("  No changes in sender table between these snapshots")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python scripts/validator-watch.py",
        description="Surface per-sender reason reuse alerts from kibble snapshots",
    )
    parser.add_argument("--watch", action="store_true", help="show only alerts (one-reason, low-diversity)")
    parser.add_argument("--file", type=str, help="specific snapshot file to analyze")
    parser.add_argument("--delta", nargs=2, metavar=("FILE_A", "FILE_B"),
                        help="compare sender tables between two snapshots")
    args = parser.parse_args(argv)

    if args.delta:
        cmd_delta(args)
    else:
        cmd_watch(args)


if __name__ == "__main__":
    sys.exit(main())
