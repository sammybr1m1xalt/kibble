#!/usr/bin/env python3
"""
snapshot-query — read and verify kibble snapshots from out/snapshots/.

Usage:
    python scripts/snapshot-query.py                       # list all snapshots
    python scripts/snapshot-query.py --latest              # show latest
    python scripts/snapshot-query.py --verify              # verify all
    python scripts/snapshot-query.py --verify <file>       # verify one
    python scripts/snapshot-query.py --since 20260906      # filter by date
    python scripts/snapshot_query.py --stats <file>        # show stats only
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = REPO_DIR / "out" / "snapshots"


def load_snapshots() -> list[Path]:
    return sorted(SNAPSHOT_DIR.glob("kibble-snapshot-*.json"))


def load_snapshot(path: Path) -> dict:
    return json.loads(path.read_text())


def verify_snapshot_file(path: Path) -> dict:
    """Verify a snapshot file. Returns dict with verification result."""
    from kibble_verifier import verify_snapshot
    snap = load_snapshot(path)
    did = snap.get("did", "")
    snap_hash = snap.get("snapshot_hash", "")
    sig = snap.get("signature", "")
    stats = snap.get("stats", {})
    ok = verify_snapshot(did, snap_hash, sig, stats)
    return {
        "file": path.name,
        "did": did,
        "hash": snap_hash,
        "verified": ok,
        "timestamp": snap.get("run_ts", ""),
        "published": snap.get("published", False),
        "stats": stats,
    }


def fmt_ts(ts: str) -> str:
    try:
        dt = datetime.strptime(ts, "%Y%m%dT%H%M%SZ")
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return ts


def cmd_list(args):
    snaps = load_snapshots()
    if not snaps:
        print("No snapshots found in out/snapshots/")
        return
    print(f"Snapshots ({len(snaps)}):")
    for p in snaps:
        snap = load_snapshot(p)
        print(
            f"  {p.name}"
            f"  ts={fmt_ts(snap.get('run_ts',''))}"
            f"  did={snap.get('did','')[:40]}..."
            f"  jobs={snap.get('stats',{}).get('job_count','?')}"
            f"  verdict={snap.get('stats',{}).get('verdict_coverage_pct','?')}%"
            f"  published={snap.get('published',False)}"
        )


def cmd_latest(args):
    snaps = load_snapshots()
    if not snaps:
        print("No snapshots found.")
        return
    p = snaps[-1]
    snap = load_snapshot(p)
    print(f"Latest snapshot: {p.name}")
    print(f"  Timestamp:   {fmt_ts(snap.get('run_ts',''))}")
    print(f"  DID:         {snap.get('did','')}")
    print(f"  Hash:        {snap.get('snapshot_hash','')[:32]}...")
    print(f"  Signature:   {snap.get('signature','')[:40]}...")
    print(f"  Published:   {snap.get('published',False)}")
    print()
    print("Stats:")
    for k, v in snap.get("stats", {}).items():
        if isinstance(v, (int, float)):
            print(f"  {k}: {v}")
        elif isinstance(v, list):
            print(f"  {k}: [{len(v)} entries]")
    print()
    # Verify
    from kibble_verifier import verify_snapshot
    ok = verify_snapshot(
        snap.get("did", ""),
        snap.get("snapshot_hash", ""),
        snap.get("signature", ""),
        snap.get("stats", {}),
    )
    print(f"  Verify:      {'✓ VALID' if ok else '✗ INVALID'}")


def cmd_verify(args):
    if args.file:
        paths = [Path(args.file)]
    else:
        paths = load_snapshots()
    if not paths:
        print("No snapshots to verify.")
        return
    results = []
    for p in paths:
        r = verify_snapshot_file(p)
        results.append(r)
        status = "✓ VALID" if r["verified"] else "✗ INVALID"
        print(f"  {r['file']}: {status}  did={r['did'][:30]}...  ts={fmt_ts(r['timestamp'])}")
    if not args.file:
        valid = sum(1 for r in results if r["verified"])
        print(f"\nSummary: {valid}/{len(results)} snapshots verified")


def cmd_since(args):
    snaps = load_snapshots()
    cutoff = args.since
    filtered = [p for p in snaps if p.name >= f"kibble-snapshot-{cutoff}"]
    if not filtered:
        print(f"No snapshots since {cutoff}")
        return
    print(f"Snapshots since {cutoff} ({len(filtered)}):")
    for p in filtered:
        snap = load_snapshot(p)
        print(
            f"  {p.name}"
            f"  ts={fmt_ts(snap.get('run_ts',''))}"
            f"  jobs={snap.get('stats',{}).get('job_count','?')}"
            f"  verdict={snap.get('stats',{}).get('verdict_coverage_pct','?')}%"
        )


def cmd_stats(args):
    p = Path(args.file)
    if not p.exists():
        print(f"File not found: {p}")
        return
    snap = load_snapshot(p)
    print(f"Stats for {p.name}:")
    print(json.dumps(snap.get("stats", {}), indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python scripts/snapshot-query.py",
        description="Read and verify kibble snapshots",
    )
    parser.add_argument(
        "--latest", action="store_true", help="show latest snapshot details"
    )
    parser.add_argument(
        "--verify", nargs="?", const="", help="verify snapshot(s); optional file path"
    )
    parser.add_argument(
        "--since", type=str, help="filter snapshots by timestamp prefix (YYYYMMDD)"
    )
    parser.add_argument(
        "--stats", type=str, help="show stats JSON for a specific snapshot file"
    )
    parser.add_argument(
        "--file", type=str, help="specific snapshot file to operate on"
    )
    args = parser.parse_args(argv)

    if args.latest:
        cmd_latest(args)
    elif args.verify is not None:
        file_arg = args.verify if args.verify != "" else None
        if file_arg:
            args.file = file_arg
        cmd_verify(args)
    elif args.since:
        cmd_since(args)
    elif args.stats:
        args.file = args.stats
        cmd_stats(args)
    else:
        cmd_list(args)


if __name__ == "__main__":
    sys.exit(main())
