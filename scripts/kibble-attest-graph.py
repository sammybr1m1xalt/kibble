#!/usr/bin/env python3
"""
kibble-attest-graph — treat ATTEST as a social graph, not a score.

Priority 4 (design doc): map the attestation graph, flag closed loops,
rank validators by distinct jobs / reasons / counterparties, and emit a
signed deny/watch list of keys whose ATTEST adds no information.

This does NOT collapse anything into a single reputation number.

Usage:
    .venv/bin/python scripts/kibble-attest-graph.py
    .venv/bin/python scripts/kibble-attest-graph.py --snapshot /path/to/export.jsonl
    .venv/bin/python scripts/kibble-attest-graph.py --deny-list-out deny-list.json

The deny/watch list is a signed JSON note, not a moral score. It lists keys
whose ATTESTs are information-free (same reason across many jobs, closed
attest loops with another key, etc.). The list is signed with the local
identity if available; otherwise it is unsigned.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

TECHNOCORE_BASE = "https://technocore.chat"
KIBBLE_EXPORT = f"{TECHNOCORE_BASE}/r/kibble/export"
REPO_DIR = Path(__file__).resolve().parent.parent
IDENTITY_PATH = REPO_DIR / "identity.pem"

sys.path.insert(0, str(REPO_DIR))
from kibble_verifier import (
    fetch_export,
    load_identity,
    load_passphrase_from_env,
    load_passphrase_from_file,
    derive_did,
    sign_snapshot,
    zero_passphrase,
)


def load_rows(path=None):
    if path:
        data = json.loads(Path(path).read_text())
        return data.get("messages", data if isinstance(data, list) else [])
    return fetch_export()


def parse_attest(text: str):
    """Return (job_id, reason, rh_hash_or_None, body) from an ATTEST line, or None."""
    if not text.startswith("ATTEST "):
        return None
    parts = text.split(" | ", 3)
    if len(parts) < 4:
        return None
    job_id = parts[1].strip()
    verdict = parts[2].strip()
    body = parts[3].strip()
    # Extract rh:<hash> if present
    rh = None
    for token in body.split():
        if token.startswith("rh:") and len(token) > 3:
            rh = token[3:]
            break
    return {"job_id": job_id, "verdict": verdict, "body": body, "rh": rh}


def build_graph(rows: list[dict]):
    """Return attestation graph data.

    Returns:
        attests: list of parsed attest dicts with sender added
        sender_jobs: sender -> set of job_ids they attested
        sender_reasons: sender -> Counter of reason texts
        sender_rh: sender -> Counter of rh hashes
        job_senders: job_id -> set of sender DIDs
        closed_loops: list of (sender_a, sender_b, reason, job_ids) where
                      A attests B's job and B attests A's job with the same reason
    """
    attests = []
    sender_jobs = defaultdict(set)
    sender_reasons = defaultdict(lambda: defaultdict(int))
    sender_rh = defaultdict(lambda: defaultdict(int))
    job_senders = defaultdict(set)

    for row in rows:
        text = row.get("text", "")
        parsed = parse_attest(text)
        if not parsed:
            continue
        sender = row.get("from", "?")
        parsed["sender"] = sender
        parsed["seq"] = row.get("seq", "?")
        parsed["ts"] = row.get("ts", "")
        attests.append(parsed)
        sender_jobs[sender].add(parsed["job_id"])
        reason = parsed["verdict"]
        if reason:
            sender_reasons[sender][reason] += 1
        if parsed["rh"]:
            sender_rh[sender][parsed["rh"]] += 1
        job_senders[parsed["job_id"]].add(sender)

    # Detect closed loops: for every pair of senders (A, B), find jobs where
    # A attested and B also attested the same job with the same reason.
    # A "closed loop" is when A attests a job that B Claimed/Delivered,
    # and B attests a job that A Claimed/Delivered, both with the same reason.
    closed_loops = []
    senders = list(sender_jobs.keys())
    for i, sa in enumerate(senders):
        for sb in senders[i + 1:]:
            # Jobs where both attested
            shared_jobs = sender_jobs[sa] & sender_jobs[sb]
            if not shared_jobs:
                continue
            # Same reason on shared jobs
            sa_reasons_on_shared = {r for j in shared_jobs for r in [
                a["verdict"] for a in attests if a["sender"] == sa and a["job_id"] == j
            ]}
            sb_reasons_on_shared = {r for j in shared_jobs for r in [
                a["verdict"] for a in attests if a["sender"] == sb and a["job_id"] == j
            ]}
            common_reasons = sa_reasons_on_shared & sb_reasons_on_shared
            if common_reasons:
                closed_loops.append({
                    "sender_a": sa,
                    "sender_b": sb,
                    "shared_jobs": sorted(shared_jobs),
                    "common_reasons": sorted(common_reasons),
                })

    return {
        "attests": attests,
        "sender_jobs": dict(sender_jobs),
        "sender_reasons": {k: dict(v) for k, v in sender_reasons.items()},
        "sender_rh": {k: dict(v) for k, v in sender_rh.items()},
        "job_senders": {k: list(v) for k, v in job_senders.items()},
        "closed_loops": closed_loops,
    }


def _counterparties(sender: str, jobs: set[str], graph: dict) -> set[str]:
    """Return the set of distinct other senders who attested the same jobs as sender."""
    counterparties: set[str] = set()
    for job in jobs:
        for other in graph["job_senders"].get(job, []):
            if other != sender:
                counterparties.add(other)
    return counterparties


def rank_senders(graph: dict):
    """Rank senders by distinct jobs, distinct reasons, distinct counterparties."""
    rows = []
    for sender, jobs in graph["sender_jobs"].items():
        reasons = graph["sender_reasons"].get(sender, {})
        rh = graph["sender_rh"].get(sender, {})
        rows.append({
            "sender": sender,
            "distinct_jobs": len(jobs),
            "distinct_reasons": len(reasons),
            "distinct_rh_hashes": len(rh),
            # Counterparties: distinct other senders who attested the same jobs
            "distinct_counterparties": len(_counterparties(sender, jobs, graph)),
            "total_attests": sum(reasons.values()),
        })
    rows.sort(key=lambda r: (r["distinct_jobs"], r["distinct_reasons"]), reverse=True)
    return rows, {r["sender"]: r for r in rows}


def find_info_free_keys(graph: dict, ranks: dict, threshold_reuse: int = 5):
    """Find keys whose ATTEST adds little information.

    Criteria (all must be true):
    - Attested >= threshold_reuse jobs
    - Used the same reason for >= 80% of their attests
    - OR participated in a closed loop with another key on the same reason
    """
    info_free = []
    for sender, jobs in graph["sender_jobs"].items():
        reasons = graph["sender_reasons"].get(sender, {})
        total = sum(reasons.values())
        if total < threshold_reuse:
            continue
        max_reason_count = max(reasons.values()) if reasons else 0
        reuse_ratio = max_reason_count / total if total else 0
        in_loop = any(
            loop["sender_a"] == sender or loop["sender_b"] == sender
            for loop in graph["closed_loops"]
        )
        if reuse_ratio >= 0.8 or in_loop:
            info_free.append({
                "sender": sender,
                "total_attests": total,
                "distinct_reasons": len(reasons),
                "max_reason": max(reasons, key=reasons.get) if reasons else None,
                "max_reason_count": max_reason_count,
                "reuse_ratio": reuse_ratio,
                "in_closed_loop": in_loop,
                "reason": "low-information attest: same verdict across many jobs "
                          "or participating in a closed attest loop",
            })
    info_free.sort(key=lambda r: r["reuse_ratio"], reverse=True)
    return info_free


def write_deny_list(info_free: list[dict], did: str | None, sig_b64: str | None, out_path: Path):
    """Write a signed deny/watch list note."""
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "did": did or "unsigned",
        "signature": sig_b64 or "",
        "note": "Deny/watch list of keys whose ATTEST adds no information. "
                "This is not a reputation score; it is a filter for information-free attestations. "
                "Source: github.com/sammybr1m1xalt/kibble-verifier",
        "keys": info_free,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    return out_path


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        prog="python scripts/kibble-attest-graph.py",
        description="Attest social graph analysis: per-sender ranking, closed loops, deny list",
    )
    parser.add_argument("--snapshot", type=Path, help="path to saved export JSON")
    parser.add_argument("--deny-list-out", type=Path, help="write deny/watch list to this path")
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
    parser.add_argument("--no-sign", action="store_true", help="unsigned output")
    args = parser.parse_args(argv)

    # --- Passphrase ---
    passphrase = None
    if args.passphrase_file:
        passphrase = load_passphrase_from_file(args.passphrase_file)
        if passphrase is None:
            print(f"ERROR: passphrase file not found: {args.passphrase_file}", file=sys.stderr)
            return 1
    elif "KIBBLE_PASSPHRASE" in os.environ:
        passphrase = load_passphrase_from_env()
    else:
        print("WARNING: no passphrase — output will be unsigned", file=sys.stderr)

    print("Loading export ...", file=sys.stderr)
    rows = load_rows(args.snapshot)
    print(f"  {len(rows)} lines", file=sys.stderr)

    graph = build_graph(rows)
    ranks, rank_by_sender = rank_senders(graph)

    print(f"\n=== Attest graph ===", file=sys.stderr)
    print(f"  total ATTEST lines: {len(graph['attests'])}", file=sys.stderr)
    print(f"  distinct senders: {len(graph['sender_jobs'])}", file=sys.stderr)
    print(f"  distinct jobs attested: {len(graph['job_senders'])}", file=sys.stderr)
    print(f"  closed loops detected: {len(graph['closed_loops'])}", file=sys.stderr)

    print(f"\n=== Sender ranking (by distinct jobs, then distinct reasons) ===")
    for r in ranks[:20]:
        print(f"  {r['sender'][:40]}")
        print(f"    jobs={r['distinct_jobs']}  reasons={r['distinct_reasons']}  "
              f"rh_hashes={r['distinct_rh_hashes']}  counterparties={r['distinct_counterparties']}  "
              f"total_attests={r['total_attests']}")

    info_free = find_info_free_keys(graph, ranks)
    if info_free:
        print(f"\n=== Info-free keys (deny/watch list candidates) ===")
        for k in info_free:
            print(f"  {k['sender'][:40]}")
            print(f"    total={k['total_attests']}  reasons={k['distinct_reasons']}  "
                  f"max_reason={k['max_reason']} ({k['max_reason_count']}/{k['total_attests']})  "
                  f"reuse_ratio={k['reuse_ratio']:.2f}  in_loop={k['in_closed_loop']}")
    else:
        print("\n=== No info-free keys found ===")

    # --- Sign the deny list if requested ---
    did = None
    sig_b64 = None
    key = None
    if args.deny_list_out and passphrase and not args.no_sign:
        try:
            key = load_identity(args.identity, passphrase)
            did = derive_did(key.public_key())
            # Sign a canonical hash of the deny list payload
            payload = {
                "generated_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                "keys": info_free,
            }
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            sig_bytes = key.sign(hashlib.sha256(canonical).digest())
            sig_b64 = base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode("ascii")
        except Exception as e:
            print(f"WARNING: signing deny list failed ({e})", file=sys.stderr)

    if args.deny_list_out:
        out_path = write_deny_list(info_free, did, sig_b64, args.deny_list_out)
        print(f"\nDeny/watch list written: {out_path}", file=sys.stderr)

    # Also print the deny list as JSON to stdout (so it can be piped / posted)
    print("\n--- deny/watch list (JSON) ---")
    print(json.dumps({
        "generated_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "did": did or "unsigned",
        "signature": sig_b64 or "",
        "keys": info_free,
    }, indent=2))

    zero_passphrase(passphrase)
    return 0


if __name__ == "__main__":
    sys.exit(main())
