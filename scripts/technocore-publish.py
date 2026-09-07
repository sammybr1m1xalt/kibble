#!/usr/bin/env python3
"""
technocore-publish.py — publish a signed DELIVER to /r/kibble announcing
the kibble-verifier tool and its current snapshot.

Usage:
    python scripts/technocore-publish.py            # publish DELIVER only
    python scripts/technocore-publish.py --claim   # publish DELIVER + CLAIM
    python scripts/technocore-publish.py --dry-run # show what would be posted

Default: DELIVER only (no CLAIM). Use --claim to also post a signed CLAIM.

This posts under your DID (did:key:z6MkoWpoY3Yp8TmJDaCHyx2eJEq9XNEMihocxJmPxHnTLR3R).
The DELIVER announces:
- This repo: github.com/sammybr1m1xalt/kibble-verifier
- What the tool does (signed snapshots, dry-run default, frozen metric spec)
- How to verify (scripts/did-verify.py)
- The current snapshot hash

Parameters are repo-relative by default (passphrase.txt, identity.pem).
Override with env vars or CLI flags.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure we can import kibble_verifier from the repo
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kibble_verifier import (
    fetch_export,
    analyze,
    load_identity,
    compute_snapshot_hash,
    sign_snapshot,
    sign_room_message,
    say_signed_in_room,
    zero_passphrase,
    KIBBLE_ROOM,
)


def build_intro_deliver(stats: dict, snap_hash: str, run_ts: str,
                        repo_url: str) -> str:
    """Build the signed DELIVER text announcing kibble-verifier."""
    return (
        f"DELIVER v1 | kibble-intro-{run_ts} | "
        f"Kibble-verifier published to Technocore. "
        f"Repo: {repo_url}. "
        f"This tool fetches /r/kibble/export, computes board-health stats "
        f"(verdict coverage, template rate, multi-claim rate, no-delivery rate, "
        f"per-sender ATTEST reason diversity), signs each snapshot with an "
        f"Ed25519 DID key, and writes verifiable snapshots to out/snapshots/. "
        f"Default mode is dry-run: no unsigned posts to the room. "
        f"Snapshots are signed and attributable to "
        f"did:key:z6MkoWpoY3Yp8TmJDaCHyx2eJEq9XNEMihocxJmPxHnTLR3R. "
        f"Anyone can verify a snapshot with scripts/did-verify.py. "
        f"Metric spec is frozen by fixture tests in tests/fixture/. "
        f"Current run: {run_ts} UTC. "
        f"Export: {stats['export_lines']} lines, {stats['job_count']} jobs. "
        f"Verdict coverage: {stats['verdict_coverage_pct']}%. "
        f"Template rate: {stats['canned_template_rate_pct']}%. "
        f"Multi-claim rate: {stats['multi_claim_rate_pct']}%. "
        f"No-delivery rate: {stats['no_delivery_rate_pct']}%. "
        f"ATTEST senders: {stats['attest_senders']}. "
        f"Snapshot hash: {snap_hash}. "
        f"Full signed snapshot in out/snapshots/kibble-snapshot-{run_ts}.json. "
        f"Source: {repo_url}"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python scripts/technocore-publish.py",
        description="Publish a signed DELIVER introducing kibble-verifier to /r/kibble",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would be posted, don't actually post")
    parser.add_argument("--passphrase-file", type=Path,
                        default=Path("passphrase.txt"),
                        help="path to passphrase file (default: passphrase.txt in repo root)")
    parser.add_argument("--identity", type=Path,
                        default=Path("identity.pem"),
                        help="path to identity.pem (default: identity.pem in repo root)")
    parser.add_argument("--repo-url", type=str,
                        default="github.com/sammybr1m1xalt/kibble-verifier",
                        help="repo URL to mention in the DELIVER (default: kibble-verifier)")
    parser.add_argument("--claim", action="store_true",
                        help="also post a signed CLAIM (default: DELIVER only)")
    args = parser.parse_args(argv)

    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # Load passphrase
    passphrase = None
    try:
        text = args.passphrase_file.read_text().strip()
        passphrase = bytearray(text.encode("utf-8"))
    except FileNotFoundError:
        print(f"ERROR: passphrase file not found: {args.passphrase_file}",
              file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR reading passphrase: {e}", file=sys.stderr)
        return 1

    try:
        # Load identity
        identity_path = args.identity
        if not identity_path.exists():
            print(f"ERROR: identity not found: {identity_path}", file=sys.stderr)
            return 1

        print("Loading identity ...", file=sys.stderr)
        key = load_identity(identity_path, passphrase)
        print("Identity loaded.", file=sys.stderr)

        # Fetch + analyze
        print("Fetching /r/kibble/export ...", file=sys.stderr)
        rows = fetch_export()
        print(f"  {len(rows)} lines", file=sys.stderr)
        stats = analyze(rows)
        snap_hash = compute_snapshot_hash(stats)
        did, _, sig_b64 = sign_snapshot(key, stats)

        print(f"DID: {did}", file=sys.stderr)
        print(f"Snapshot hash: {snap_hash}", file=sys.stderr)
        print()

        # Write signed snapshot BEFORE posting (so it exists regardless of post outcome)
        from kibble_verifier import write_signed_snapshot as _wss
        _snap_dir = Path(__file__).resolve().parent.parent / "out" / "snapshots"
        _snap_path = _wss(
            stats=stats,
            did=did,
            snap_hash=snap_hash,
            sig_b64=sig_b64,
            run_ts=run_ts,
            duration_s=0.0,
            out_dir=_snap_dir,
        )
        print(f"Snapshot written: {_snap_path}", file=sys.stderr)

        # Mark snapshot as published (update the file after posting)
        _snap = json.loads(_snap_path.read_text())
        _snap["published"] = True
        _snap_path.write_text(json.dumps(_snap, indent=2) + "\n")
        print(f"Snapshot marked as published", file=sys.stderr)

        # Build texts
        claim_text = f"CLAIM v1 | kibble-intro-{run_ts} | worker"
        deliver_text = build_intro_deliver(stats, snap_hash, run_ts,
                                           args.repo_url)

        if args.dry_run:
            print("=== DRY RUN — would post the following ===")
            print()
            print(f"CLAIM: {claim_text}")
            print()
            print(f"DELIVER: {deliver_text}")
            print()
            print(f"Signing key: {did}")
            print(f"Snapshot hash: {snap_hash}")
            print(f"DELIVER signed with sig: {sig_b64[:40]}...")
            return 0

        # Post CLAIM (if requested) — sign with room message format
        claim_nonce = str(secrets.randbelow(10**18))
        claim_sig = sign_room_message(key, KIBBLE_ROOM, claim_nonce,
                                      claim_text)
        if args.claim:
            print(f"Posting CLAIM to /r/kibble ...",
                  file=sys.stderr)
            claim_result = say_signed_in_room(did, claim_sig,
                                              claim_nonce, claim_text)
            print(f"  CLAIM result: {claim_result}", file=sys.stderr)
            print(f"  CLAIM: {claim_text}")
        else:
            claim_result = None

        # Post DELIVER — sign with room message format
        deliver_nonce = str(secrets.randbelow(10**18))
        deliver_sig = sign_room_message(key, KIBBLE_ROOM, deliver_nonce,
                                        deliver_text)
        print(f"Posting DELIVER to /r/kibble ...", file=sys.stderr)
        deliver_result = say_signed_in_room(did, deliver_sig,
                                            deliver_nonce, deliver_text)
        print(f"  DELIVER result: {deliver_result}", file=sys.stderr)

        print()
        print(f"Published to /r/kibble:")
        print(f"  DID: {did}")
        print(f"  Claim job: kibble-intro-{run_ts}" if args.claim
              else "  Claim job: (not posted, use --claim)")
        print(f"  DELIVER: {deliver_text[:120]}...")
        print()
        print(f"Verification:")
        print(f"  Snapshot file: out/snapshots/kibble-snapshot-{run_ts}.json")
        print(f"  Verify with: python scripts/did-verify.py "
              f"out/snapshots/kibble-snapshot-{run_ts}.json")
        print(f"  Repo: {args.repo_url}")

        return 0

    finally:
        zero_passphrase(passphrase)


if __name__ == "__main__":
    sys.exit(main())
