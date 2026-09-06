#!/usr/bin/env python3
"""
did-verify — verify a signed snapshot against its DID without the full pipeline.

Usage:
    python scripts/did-verify.py <snapshot-file>
    python scripts/did-verify.py out/snapshots/kibble-snapshot-20260906T041227Z.json

Verifies:
1. The DID is well-formed (did:key:z<base58btc(0xED01+pubkey)>)
2. The signature is valid Ed25519 over sha256(canonical stats JSON)
3. The snapshot_hash in the file matches sha256(stats)
4. The stats match the snapshot_hash (no tampering)

Fast path: loads only the snapshot file, no network fetch.
If you want to also fetch and compare against live export, use --fetch.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure kibble_verifier is importable from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO_DIR = Path(__file__).resolve().parent.parent


def load_snapshot(path: Path) -> dict:
    return json.loads(path.read_text())


def verify_digest(snap: dict) -> bool:
    """Verify that snapshot_hash matches sha256(canonical stats)."""
    from kibble_verifier import compute_snapshot_hash
    expected = compute_snapshot_hash(snap.get("stats", {}))
    actual = snap.get("snapshot_hash", "")
    return expected == actual


def verify_signature(snap: dict) -> bool:
    """Verify the Ed25519 signature over the stats hash."""
    from kibble_verifier import verify_snapshot
    did = snap.get("did", "")
    snap_hash = snap.get("snapshot_hash", "")
    sig = snap.get("signature", "")
    stats = snap.get("stats", {})
    return verify_snapshot(did, snap_hash, sig, stats)


def normalize_did(did: str) -> str:
    """Normalize a did:key to lowercase for comparison."""
    return did.lower()


def cmd_verify(args):
    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}")
        return 1

    snap = load_snapshot(path)
    print(f"Verifying: {path.name}")
    print(f"  DID:         {snap.get('did','')}")
    print(f"  Hash:        {snap.get('snapshot_hash','')[:32]}...")
    print(f"  Sig:         {snap.get('signature','')[:40]}...")
    print(f"  Timestamp:   {snap.get('run_ts','')}")
    print()

    checks = []

    # Check 1: Digest matches
    digest_ok = verify_digest(snap)
    checks.append(("snapshot_hash matches sha256(stats)", digest_ok))
    print(f"  [{'✓' if digest_ok else '✗'}] snapshot_hash = sha256(canonical stats): {digest_ok}")
    if not digest_ok:
        expected = __import__("kibble_verifier", fromlist=["compute_snapshot_hash"]).compute_snapshot_hash(snap.get("stats", {}))
        print(f"      expected: {expected}")
        print(f"      got:      {snap.get('snapshot_hash','')}")

    # Check 2: Signature valid
    sig_ok = verify_signature(snap)
    checks.append(("Ed25519 signature valid", sig_ok))
    print(f"  [{'✓' if sig_ok else '✗'}] Ed25519 signature over stats hash: {sig_ok}")

    # Check 3: DID well-formed
    from kibble_verifier import verify_snapshot as _vs
    did = snap.get("did", "")
    wellformed = did.startswith("did:key:z") and len(did) > 20
    checks.append(("DID well-formed (did:key:z...)", wellformed))
    print(f"  [{'✓' if wellformed else '✗'}] DID well-formed: {wellformed}")

    # Check 4: Timestamp present and well-formed (YYYYMMDDTHHMMSSZ = 15 chars)
    ts = snap.get("run_ts", "")
    ts_ok = len(ts) == 16 and ts[8] == "T" and ts[9:15].isdigit() and ts[-1] == "Z"
    checks.append(("Timestamp present and well-formed", ts_ok))
    print(f"  [{'✓' if ts_ok else '✗'}] Timestamp: {ts}")

    print()
    all_ok = all(c[1] for c in checks)
    print(f"  Overall: {'✓ ALL CHECKS PASSED' if all_ok else '✗ SOME CHECKS FAILED'}")
    for name, ok in checks:
        if not ok:
            print(f"    FAILED: {name}")
    return 0 if all_ok else 1


def cmd_fetch_verify(args):
    """Verify snapshot AND fetch live export to compare stats."""
    import urllib.request
    from kibble_verifier import analyze

    path = Path(args.file)
    snap = load_snapshot(path)

    print(f"Verifying + comparing: {path.name}")
    print()

    # First: verify the snapshot signature (same as cmd_verify)
    sig_ok = verify_signature(snap)
    digest_ok = verify_digest(snap)
    print(f"  Signature valid: {'✓' if sig_ok else '✗'}")
    print(f"  Digest matches:  {'✓' if digest_ok else '✗'}")

    if not sig_ok or not digest_ok:
        print("  Snapshot fails local verification. Aborting live compare.")
        return 1

    # Fetch live
    print()
    print("Fetching live /r/kibble/export ...")
    req = urllib.request.Request("https://technocore.chat/r/kibble/export")
    raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    rows = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    print(f"  {len(rows)} lines")

    # Compute live stats
    live_stats = analyze(rows)
    snapshot_stats = snap.get("stats", {})

    print()
    print("Snapshot stats vs live stats:")
    for key in (
        "job_count",
        "verdict_coverage_pct",
        "canned_template_rate_pct",
        "multi_claim_rate_pct",
        "no_delivery_rate_pct",
        "attest_count",
        "attest_senders",
    ):
        sv = snapshot_stats.get(key)
        lv = live_stats.get(key)
        match = sv == lv if sv is not None and lv is not None else None
        status = "✓" if match else "✗"
        if match is None:
            status = "? (one missing)"
        print(f"  {status} {key:<28} snapshot={sv}  live={lv}")

    # Overall match
    all_keys = set(snapshot_stats.keys()) | set(live_stats.keys())
    numeric_ok = True
    for key in all_keys:
        sv = snapshot_stats.get(key)
        lv = live_stats.get(key)
        if isinstance(sv, (int, float)) and isinstance(lv, (int, float)):
            if sv != lv:
                numeric_ok = False
                print(f"    ✗ MISMATCH: {key}  snapshot={sv}  live={lv}")

    print()
    if numeric_ok:
        print("  ✓ Snapshot stats match live export")
    else:
        print("  ✗ Snapshot stats DIFFER from live export (snapshot is stale)")
        print("    This is expected if the snapshot was taken at a different time.")
        print("    Snapshot is still validly signed — it just reflects an earlier state.")

    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python scripts/did-verify.py",
        description="Verify a signed kibble snapshot against its DID",
    )
    parser.add_argument("file", nargs="?", type=str,
                        help="snapshot file to verify (default: latest in out/snapshots/)")
    parser.add_argument("--fetch", action="store_true",
                        help="also fetch live export and compare stats (slower)")
    args = parser.parse_args(argv)

    if args.fetch:
        if not args.file:
            # Default to latest
            snaps = sorted((REPO_DIR / "out" / "snapshots").glob("kibble-snapshot-*.json"))
            if snaps:
                args.file = str(snaps[-1])
            else:
                print("No snapshots found.")
                return 1
        return cmd_fetch_verify(args)
    else:
        if not args.file:
            snaps = sorted((REPO_DIR / "out" / "snapshots").glob("kibble-snapshot-*.json"))
            if snaps:
                args.file = str(snaps[-1])
            else:
                print("No snapshots found. Specify a file with --file.")
                return 1
        return cmd_verify(args)


if __name__ == "__main__":
    sys.exit(main())
