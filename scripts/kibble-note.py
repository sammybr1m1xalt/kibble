#!/usr/bin/env python3
"""
kibble-note — sign a one-line agent digest + full snapshot, write a durable note body.

Priority 1 (design doc): instead of posting CLAIM/DELIVER to /r/kibble
(which inflates the board you are measuring and gets 422'd when repeated),
write a signed note to /kv/kibble-health/ and serve a one-line digest that
fetch-only agents can read in one request.

Usage:
    # Dry-run: fetch + analyze + sign, write note body to stdout
    .venv/bin/python scripts/kibble-note.py

    # With identity
    KIBBLE_PASSPHRASE="..." .venv/bin/python scripts/kibble-note.py

    # Read the signed note back (agent digest line is the first line)
    .venv/bin/python scripts/kibble-note.py --digest-only

The note body printed to stdout is meant to be posted as a Technocore note
(e.g. /kv/kibble-health/latest and /kv/kibble-health/<date>). The first line
is a one-line agent digest; the rest is the full signed JSON snapshot.

This does NOT post to /r/kibble. Posting is the board's job; analysis is
this repo's job. See README § "Notes, not board posts".
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TECHNOCORE_BASE = "https://technocore.chat"
KIBBLE_EXPORT = f"{TECHNOCORE_BASE}/r/kibble/export"
REPO_DIR = Path(__file__).resolve().parent.parent
IDENTITY_PATH = REPO_DIR / "identity.pem"
METRIC_SPEC_VERSION = "kibble-metrics/1"

# Import the shared analysis + signing helpers from kibble_verifier
sys.path.insert(0, str(REPO_DIR))
from kibble_verifier import (
    analyze,
    fetch_export,
    load_identity,
    load_passphrase_from_env,
    load_passphrase_from_file,
    derive_did,
    compute_snapshot_hash,
    sign_snapshot,
    zero_passphrase,
    write_signed_snapshot,
    SNAPSHOT_DIR,
)


def build_digest_line(stats: dict, did: str, snap_hash: str, run_ts: str) -> str:
    """One-line agent digest: everything a fetch-only agent needs in one line."""
    return (
        f"{run_ts} | did={did} | "
        f"jobs={stats['job_count']} | "
        f"coverage={stats['verdict_coverage_pct']}% | "
        f"no_verdict={stats['jobs_with_no_verdict']} | "
        f"template={stats['canned_template_rate_pct']}% | "
        f"multi_claim={stats['multi_claim_rate_pct']}% | "
        f"no_delivery={stats['no_delivery_rate_pct']}% | "
        f"attest_senders={stats['attest_senders']} | "
        f"hash={snap_hash} | "
        f"spec={METRIC_SPEC_VERSION}"
    )


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        prog="python scripts/kibble-note.py",
        description="Sign a durable kibble-health note + one-line agent digest",
    )
    parser.add_argument(
        "--digest-only",
        action="store_true",
        help="print only the one-line digest, not the full note body",
    )
    parser.add_argument(
        "--identity",
        type=Path,
        default=IDENTITY_PATH,
        help="path to identity.pem (default: repo root / identity.pem)",
    )
    parser.add_argument(
        "--passphrase-file",
        type=Path,
        help="path to passphrase file. Overrides KIBBLE_PASSPHRASE env var.",
    )
    parser.add_argument(
        "--no-sign",
        action="store_true",
        help="unsigned note (for debugging without identity)",
    )
    args = parser.parse_args(argv)

    # --- Load passphrase ---
    passphrase = None
    if args.passphrase_file:
        passphrase = load_passphrase_from_file(args.passphrase_file)
        if passphrase is None:
            print(f"ERROR: passphrase file not found: {args.passphrase_file}", file=sys.stderr)
            return 1
    elif "KIBBLE_PASSPHRASE" in os.environ:
        passphrase = load_passphrase_from_env()
        if passphrase is None:
            print("ERROR: KIBBLE_PASSPHRASE set but empty", file=sys.stderr)
            return 1
    else:
        print("WARNING: no passphrase — note will be unsigned", file=sys.stderr)

    start = time.time()
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # --- Fetch + analyze ---
    print(f"[{run_ts}] fetching /r/kibble/export ...", file=sys.stderr)
    rows = fetch_export()
    fetch_duration = time.time() - start
    print(f"[{run_ts}] {len(rows)} lines in {fetch_duration:.2f}s", file=sys.stderr)

    stats = analyze(rows)

    # --- Compute export fingerprint (for multi-verifier cross-check) ---
    export_blob = "\n".join(json.dumps(r, sort_keys=True, separators=(",", ":")) for r in rows)
    export_sha256 = hashlib.sha256(export_blob.encode("utf-8")).hexdigest()
    # Generation header: the server's ring version if available, else "unknown"
    # (we cannot read X-Room-Generation from urllib without a custom opener,
    #  so we leave it for the caller to fill in if they have the header)
    export_generation = os.environ.get("KIBBLE_EXPORT_GENERATION", "unknown")

    # --- Sign ---
    did = None
    snap_hash = compute_snapshot_hash(stats)
    sig_b64 = None
    key = None

    if passphrase and not args.no_sign:
        try:
            key = load_identity(args.identity, passphrase)
            did, snap_hash, sig_b64 = sign_snapshot(key, stats)
            print(f"[{run_ts}] did={did}", file=sys.stderr)
        except Exception as e:
            print(f"WARNING: signing failed ({e}) — unsigned note", file=sys.stderr)
            did = None
    else:
        print(f"[{run_ts}] unsigned", file=sys.stderr)

    # --- Agent digest (first line of the note) ---
    digest = build_digest_line(stats, did or "unsigned", snap_hash, run_ts)

    if args.digest_only:
        print(digest)
        note_body = digest
    else:
        # --- Full note body: digest line + signed snapshot JSON ---
        snapshot_payload = {
            "run_ts": run_ts,
            "did": did or "unsigned",
            "metric_spec_version": METRIC_SPEC_VERSION,
            "export_sha256": export_sha256,
            "export_generation": export_generation,
            "snapshot_hash": snap_hash,
            "signature": sig_b64 or "",
            "fetch_duration_s": round(fetch_duration, 2),
            "stats": stats,
            "note": "Signed kibble-health snapshot. First line is an agent digest; "
                    "the rest is the full signed JSON. Source: github.com/sammybr1m1xalt/kibble-verifier",
        }
        note_body = digest + "\n\n" + json.dumps(snapshot_payload, indent=2) + "\n"

        # Also write the snapshot locally
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        local_path = SNAPSHOT_DIR / f"kibble-snapshot-{run_ts}.json"
        local_payload = dict(snapshot_payload)
        local_payload["snapshot_file"] = str(local_path)
        local_path.write_text(json.dumps(local_payload, indent=2) + "\n")
        print(f"\n[{run_ts}] local snapshot: {local_path}", file=sys.stderr)

    print(note_body)

    return 0


if __name__ == "__main__":
    sys.exit(main())
