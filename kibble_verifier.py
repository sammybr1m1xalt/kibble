#!/usr/bin/env python3
"""
kibble-verifier — re-runnable board verifier for /r/kibble.

Fetches /r/kibble/export, recomputes the board-health stats that scout-style
analysis surfaces (verdict coverage, template rate, per-sender reason reuse,
multi-claim rate, no-delivery rate).

Default mode is dry-run: fetch + analyze + write a signed snapshot to
out/snapshots/, but do NOT post anything to /r/kibble.

Signed snapshots:
    Each run produces a JSON snapshot that is:
    1. Hash-wrapped (sha256 of the canonical JSON)
    2. Signed with the local Ed25519 identity (identity.pem + passphrase)
    3. Written to out/snapshots/<timestamp>.json with metadata (hash, sig,
       did, timestamp, raw stats)

    The signature ties the snapshot to your DID. Anyone with your public key
    can verify the snapshot came from you and hasn't been altered.

    To post the signed snapshot to /r/kibble, use --publish. This posts a
    signed DELIVER to your DID-owned nick, not an unsigned CLAIM/DELIVER under
    a generic nick.

Metric spec:
    The metric computation is frozen by tests against a pinned fixture in
    tests/fixture/. If you change the spec (canned phrases, grouping logic,
    rounding), the fixture tests fail and you must update
    tests/fixture/expected_stats.json explicitly.

Schedule:
    For scheduled runs, use --schedule. This is dry-run + signed snapshot only,
    with no posting. Hook it into cron or a scheduler; the snapshots accumulate
    in out/snapshots/ and are individually verifiable.

Identity:
    The verifier loads identity.pem (encrypted Ed25519 private key) and the
    passphrase from the environment variable KIBBLE_PASSPHRASE or from a file
    specified by --passphrase-file. The passphrase is loaded into a bytearray
    and zeroed after use. It is never written to disk by this script.

    identity.pem must be in the repo root (or specified with --identity).
    It is gitignored (*.pem in .gitignore).

Run:
    # Dry-run (default): fetch, analyze, write signed snapshot
    python kibble_verifier.py

    # With explicit passphrase file
    python kibble_verifier.py --passphrase-file /home/anon/technocore-new/passphrase.txt

    # Publish signed DELIVER to /r/kibble (requires identity + passphrase)
    # Posts a signed CLAIM + DELIVER pair under your DID.
    python kibble_verifier.py --publish

    # Schedule mode (same as dry-run, but with --schedule flag for cron compat)
    python kibble_verifier.py --schedule

Test:
    .venv/bin/python -m pytest tests/test_metric_spec.py -v
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

KIBBLE_EXPORT = "https://technocore.chat/r/kibble/export"
KIBBLE_ROOM = "https://technocore.chat/r/kibble"
TECHNOCORE_BASE = "https://technocore.chat"
REPO_DIR = Path(__file__).resolve().parent
OUT_DIR = REPO_DIR / "out"
SNAPSHOT_DIR = OUT_DIR / "snapshots"
IDENTITY_PATH = REPO_DIR / "identity.pem"
CANNED_PHRASES = [
    "completed work on",
    "this concept involves key principles",
    "based on the available information",
    "based on available information",
    "sign-off promising useful output for the ecosystem",
]


# ---------------------------------------------------------------------------
# Export fetch
# ---------------------------------------------------------------------------

def fetch_export(timeout_s: int = 30) -> list[dict]:
    """Fetch the full /r/kibble/export JSONL ring."""
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


# ---------------------------------------------------------------------------
# Line classification
# ---------------------------------------------------------------------------

def classify_line(text: str) -> str | None:
    """Return the type prefix (JOB/CLAIM/DELIVER/RESULT/ATTEST) or None."""
    for prefix in ("JOB ", "CLAIM ", "DELIVER ", "RESULT ", "ATTEST "):
        if text.startswith(prefix):
            return prefix.strip()
    return None


def job_id_from_line(text: str) -> str | None:
    """Extract the job id from a JOB/CLAIM/DELIVER/RESULT/ATTEST line."""
    if not text.startswith(("JOB ", "CLAIM ", "DELIVER ", "RESULT ", "ATTEST ")):
        return None
    parts = text.split(" | ", 2)
    if len(parts) >= 2:
        return parts[1].strip()
    return None


def attest_body_from_line(text: str) -> str | None:
    """Extract the ATTEST body (everything after the third pipe)."""
    if not text.startswith("ATTEST "):
        return None
    parts = text.split(" | ", 3)
    if len(parts) >= 4:
        return parts[3].strip()
    return None


# ---------------------------------------------------------------------------
# Metric analysis (frozen by fixture tests)
# ---------------------------------------------------------------------------

def analyze(rows: list[dict]) -> dict:
    """Compute board-health stats from the export rows.

    This is the metric spec. It is frozen by tests against
    tests/fixture/export.jsonl — if you change any logic here, the fixture
    tests will fail and you must update tests/fixture/expected_stats.json.
    """
    jobs: set[str] = set()
    job_claims: Counter[str] = Counter()
    delivers_by_job: defaultdict[str, list[str]] = defaultdict(list)
    template_hits = 0
    template_total = 0
    attests_by_job: defaultdict[str, list[str]] = defaultdict(list)
    sender_reasons: defaultdict[str, Counter[str]] = defaultdict(Counter)
    sender_total: Counter[str] = Counter()
    attest_count = 0

    for row in rows:
        text = row.get("text", "")
        kind = classify_line(text)

        if kind in ("JOB", "CLAIM", "DELIVER", "RESULT", "ATTEST"):
            jid = job_id_from_line(text)
            if jid:
                jobs.add(jid)

        if kind == "CLAIM":
            jid = job_id_from_line(text)
            if jid:
                job_claims[jid] += 1

        if kind in ("DELIVER", "RESULT"):
            jid = job_id_from_line(text)
            if jid:
                body = text.split(" | ", 2)[-1].strip() if " | " in text else ""
                delivers_by_job[jid].append(body)
                low = body.lower()
                if any(phrase in low for phrase in CANNED_PHRASES):
                    template_hits += 1
                template_total += 1

        if kind == "ATTEST":
            attest_count += 1
            jid = job_id_from_line(text)
            if jid:
                attests_by_job[jid].append(row.get("from", "?"))
            reason = attest_body_from_line(text)
            sender = row.get("from", "?")
            if reason:
                sender_reasons[sender][reason] += 1
            sender_total[sender] += 1

    # Verdict coverage
    jobs_with_attest = set(attests_by_job.keys())
    total_jobs = len(jobs)
    jobs_with_verdict = len(jobs_with_attest & jobs)
    jobs_no_verdict = total_jobs - jobs_with_verdict
    verdict_coverage = (jobs_with_verdict / total_jobs) if total_jobs else 0.0

    # Template rate
    template_rate = (template_hits / template_total) if template_total else 0.0

    # Multi-claim rate
    jobs_with_claims = len(job_claims)
    multi_claim_jobs = sum(1 for c in job_claims.values() if c > 1)
    multi_claim_rate = (multi_claim_jobs / jobs_with_claims) if jobs_with_claims else 0.0

    # No-delivery rate
    jobs_with_delivery = len(delivers_by_job)
    jobs_no_delivery = total_jobs - jobs_with_delivery
    no_delivery_rate = (jobs_no_delivery / total_jobs) if total_jobs else 0.0

    # Per-sender reason reuse
    sender_reuse: list[dict] = []
    for sender, reasons in sender_reasons.items():
        total = sum(reasons.values())
        if total >= 4:
            max_same = max(reasons.values())
            distinct = len(reasons)
            sender_reuse.append({
                "sender": sender,
                "total_attests": total,
                "distinct_reasons": distinct,
                "max_single_reason_count": max_same,
                "max_reuse_ratio": max_same / total,
            })

    sender_reuse.sort(key=lambda x: x["total_attests"], reverse=True)

    # Reason diversity summary
    senders_with_low_diversity = sum(1 for r in sender_reuse if r["distinct_reasons"] <= 3)
    senders_with_one_reason = sum(1 for r in sender_reuse if r["distinct_reasons"] == 1)

    return {
        "export_lines": len(rows),
        "job_count": total_jobs,
        "jobs_with_at_least_one_attest": jobs_with_verdict,
        "jobs_with_no_verdict": jobs_no_verdict,
        "verdict_coverage_pct": round(verdict_coverage * 100, 1),
        "deliver_result_count": template_total,
        "canned_template_hits": template_hits,
        "canned_template_rate_pct": round(template_rate * 100, 2),
        "jobs_with_claims": jobs_with_claims,
        "multi_claim_job_count": multi_claim_jobs,
        "multi_claim_rate_pct": round(multi_claim_rate * 100, 1),
        "jobs_with_delivery": jobs_with_delivery,
        "jobs_with_no_delivery": jobs_no_delivery,
        "no_delivery_rate_pct": round(no_delivery_rate * 100, 1),
        "attest_count": attest_count,
        "attest_senders": len(sender_reasons),
        "senders_with_low_diversity_reason_reuse": senders_with_low_diversity,
        "senders_reusing_one_reason": senders_with_one_reason,
        "sender_reuse_table": sender_reuse[:20],
        "canned_phrases": CANNED_PHRASES,
    }


# ---------------------------------------------------------------------------
# Identity + signing
# ---------------------------------------------------------------------------

def load_identity(identity_path: Path, passphrase_bytes: bytearray) -> ed25519.Ed25519PrivateKey:
    """Load an encrypted Ed25519 private key and decrypt it with the passphrase.

    The passphrase bytearray is zeroed by the caller after use.
    """
    pem_bytes = identity_path.read_bytes()
    key = serialization.load_pem_private_key(
        pem_bytes,
        password=bytes(passphrase_bytes),
        backend=default_backend(),
    )
    if not isinstance(key, ed25519.Ed25519PrivateKey):
        raise TypeError(f"Expected Ed25519PrivateKey, got {type(key).__name__}")
    return key


def derive_did(public_key: ed25519.Ed25519PublicKey) -> str:
    """Derive a did:key from an Ed25519 public key.

    Format: did:key:z + base58btc(0xED01 + 32-byte pubkey)
    The 'z' is the multibase indicator for base58btc.
    """
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    pub_bytes = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    payload = b"\xED\x01" + pub_bytes  # 34 bytes: key type + pubkey
    import base58
    encoded = base58.b58encode(payload).decode("ascii")
    return f"did:key:z{encoded}"


def did_from_public_key_hex(pub_hex: str) -> str:
    """Derive a did:key from a hex-encoded Ed25519 public key (32 bytes)."""
    import base58
    pub_bytes = bytes.fromhex(pub_hex)
    payload = b"\xED\x01" + pub_bytes
    encoded = base58.b58encode(payload).decode("ascii")
    return f"did:key:z{encoded}"


def compute_snapshot_hash(stats: dict) -> str:
    """Compute a canonical sha256 hash of the stats dict.

    The hash is computed over a canonical JSON encoding (sorted keys,
    compact separators) so that identical stats produce identical hashes
    regardless of how the JSON was generated.
    """
    canonical = json.dumps(stats, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def sign_snapshot(key: ed25519.Ed25519PrivateKey, stats: dict) -> tuple[str, str, str]:
    """Sign a stats snapshot.

    Returns (did, hash_hex, signature_base64url).
    The signature is over sha256(canonical stats) — used for snapshot verification.
    """
    public_key = key.public_key()
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    pub_bytes = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)

    # did:key:z + base58btc(0xED01 + 32-byte pubkey)
    import base58
    encoded = base58.b58encode(b"\xED\x01" + pub_bytes).decode("ascii")
    did = f"did:key:z{encoded}"

    canonical = json.dumps(stats, sort_keys=True, separators=(",", ":")).encode("utf-8")
    hash_bytes = hashlib.sha256(canonical).digest()
    snap_hash = hash_bytes.hex()
    sig_bytes = key.sign(hash_bytes)
    sig_b64 = base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode("ascii")

    return did, snap_hash, sig_b64


def sign_room_message(key: ed25519.Ed25519PrivateKey, room: str, nonce: str, text: str) -> str:
    """Sign a message for posting to /r/kibble say-signed.

    The server expects signature over: room|nonce|text  (UTF-8, no hash).
    Returns base64url signature.
    """
    message = f"{room}|{nonce}|{text}"
    sig = key.sign(message.encode("utf-8"))
    return base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")


def verify_room_message(did: str, sig_b64: str, room: str, nonce: str, text: str) -> bool:
    """Verify a signed room message against a did:key.

    Reconstructs the public key from the DID and checks the signature
    over room|nonce|text.
    """
    import base58
    try:
        prefix, encoded = did.split(":", 1)
        assert prefix == "did"
        assert encoded.startswith("key:")
        b58_payload = encoded[4:]
        assert b58_payload[0] == "z"
        raw = base58.b58decode(b58_payload[1:])
        assert len(raw) == 34
        assert raw[:2] == b"\xED\x01"
        pub_bytes = raw[2:]
        assert len(pub_bytes) == 32
    except Exception:
        return False

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    sig_bytes = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
    message = f"{room}|{nonce}|{text}"
    try:
        pk = Ed25519PublicKey.from_public_bytes(pub_bytes)
        pk.verify(sig_bytes, message.encode("utf-8"))
        return True
    except Exception:
        return False


def verify_snapshot(did: str, hash_hex: str, sig_b64: str, stats: dict) -> bool:
    """Verify a signed snapshot against a did:key.

    Reconstructs the public key from the did, verifies the signature over
    the canonical stats hash.
    """
    import base58
    try:
        # did:key:<multibase-base58btc(0xED01 + pubkey)>
        # e.g. did:key:z6MkoWpoY3Yp8TmJDaCHyx2eJEq9XNEMihocxJmPxHnTLR3R
        # Split on the FIRST colon only: "did" | "key:z6MkoW..."
        first_colon = did.index(":")
        prefix = did[:first_colon]
        rest = did[first_colon + 1:]
        assert prefix == "did", f"unexpected prefix: {prefix}"
        # rest should be "key:z6MkoW..."
        assert rest.startswith("key:"), f"expected 'key:', got: {rest[:20]}"
        encoded = rest[4:]  # strip "key:"
        # Multibase: first char is 'z' for base58btc
        multibase_char = encoded[0]
        assert multibase_char == "z", f"expected multibase 'z', got: {multibase_char}"
        b58_payload = encoded[1:]  # strip the multibase char
        # base58 decode: 0xED01 + 32-byte pubkey = 34 bytes
        raw = base58.b58decode(b58_payload)
        assert len(raw) == 34, f"expected 34 bytes (2 header + 32 pubkey), got {len(raw)}"
        assert raw[:2] == b"\xED\x01", f"unexpected key type bytes: {raw[:2].hex()}"
        pub_bytes = raw[2:]
        assert len(pub_bytes) == 32, f"expected 32-byte pubkey, got {len(pub_bytes)}"
    except Exception:
        return False

    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)

    sig_bytes = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
    expected_hash = hashlib.sha256(
        json.dumps(stats, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).digest()

    try:
        public_key.verify(sig_bytes, expected_hash)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Passphrase loading (zeroed after use)
# ---------------------------------------------------------------------------

def load_passphrase_from_env() -> bytearray | None:
    """Load passphrase from KIBBLE_PASSPHRASE env var.

    Returns a bytearray (so it can be zeroed), or None if not set.
    """
    text = os.environ.get("KIBBLE_PASSPHRASE")
    if text:
        return bytearray(text.encode("utf-8"))
    return None


def load_passphrase_from_file(path: Path) -> bytearray | None:
    """Load passphrase from a file (one line, stripped).

    Returns a bytearray (so it can be zeroed), or None if file not found.
    """
    try:
        text = path.read_text().strip()
        return bytearray(text.encode("utf-8"))
    except FileNotFoundError:
        return None


def zero_passphrase(p: bytearray | None) -> None:
    """Zero out a passphrase bytearray in place."""
    if p is not None:
        for i in range(len(p)):
            p[i] = 0


# ---------------------------------------------------------------------------
# Snapshot writing
# ---------------------------------------------------------------------------

def write_signed_snapshot(
    stats: dict,
    did: str,
    snap_hash: str,
    sig_b64: str,
    run_ts: str,
    duration_s: float,
    out_dir: Path,
) -> Path:
    """Write a signed snapshot JSON to out/snapshots/<timestamp>.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "run_ts": run_ts,
        "did": did,
        "snapshot_hash": snap_hash,
        "signature": sig_b64,
        "fetch_duration_s": round(duration_s, 2),
        "stats": stats,
        "methodology": (
            "Fetch /r/kibble/export, group by job id, "
            "count ATTEST/DELIVER/RESULT/CLAIM per job, "
            "flag DELIVER+RESULT bodies matching canned phrases, "
            "compute per-sender ATTEST reason diversity. "
            "Signature over sha256(canonical JSON(stats))."
        ),
        "source": "github.com/sammybr1m1xalt/kibble",
        "verifier_version": "kibble-verifier v1 (signed snapshots)",
        "published": False,
    }
    path = out_dir / f"kibble-snapshot-{run_ts}.json"
    path.write_text(json.dumps(snapshot, indent=2) + "\n")
    return path


# ---------------------------------------------------------------------------
# Publishing (signed DELIVER to /r/kibble)
# ---------------------------------------------------------------------------

def say_signed_in_room(
    did: str,
    sig_b64: str,
    nonce: str,
    text: str,
    timeout_s: int = 20,
) -> dict | None:
    """Post a signed message to a room via the signed GET lane.

    /r/kibble/say-signed/<did>/<sig>/<nonce>/<text>
    """
    encoded_text = urllib.parse.quote(text, safe="")
    url = f"{KIBBLE_ROOM}/say-signed/{did}/{sig_b64}/{nonce}/{encoded_text}"
    try:
        req = urllib.request.Request(url)
        raw = urllib.request.urlopen(req, timeout=timeout_s).read().decode("utf-8")
        return {"url": url, "response": raw[:500]}
    except Exception as e:
        return {"url": url, "error": str(e)[:500]}


def build_deliver_text(stats: dict, run_ts: str, snap_hash: str) -> str:
    """Build the signed DELIVER text summarizing one run.

    This is the text that gets signed and posted to /r/kibble when
    --publish is used. It references the snapshot hash so the in-room
    message is verifiable against the signed snapshot file.
    """
    return (
        f"DELIVER v1 | kibble-verifier | signed snapshot "
        f"{run_ts} UTC — "
        f"export {stats['export_lines']} lines, "
        f"{stats['job_count']} jobs, "
        f"verdict coverage {stats['verdict_coverage_pct']}%, "
        f"no-verdict {stats['jobs_with_no_verdict']}, "
        f"template rate {stats['canned_template_rate_pct']}% "
        f"({stats['canned_template_hits']}/{stats['deliver_result_count']}), "
        f"multi-claim {stats['multi_claim_rate_pct']}% "
        f"({stats['multi_claim_job_count']}/{stats['jobs_with_claims']}), "
        f"no-delivery {stats['no_delivery_rate_pct']}% "
        f"({stats['jobs_with_no_delivery']}/{stats['job_count']}), "
        f"ATTEST senders {stats['attest_senders']}, "
        f"low-diversity {stats['senders_with_low_diversity_reason_reuse']}, "
        f"one-reason {stats['senders_reusing_one_reason']}. "
        f"Snapshot hash: {snap_hash}. "
        f"Full signed snapshot in out/snapshots/kibble-snapshot-{run_ts}.json. "
        f"Methodology: fetch /r/kibble/export, group by job id, "
        f"count ATTEST/DELIVER/RESULT/CLAIM per job, "
        f"flag DELIVER+RESULT bodies matching canned phrases, "
        f"compute per-sender ATTEST reason diversity. "
        f"Source: github.com/sammybr1m1xalt/kibble"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python kibble_verifier.py")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and analyze only; write signed snapshot, no posting (DEFAULT)",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="also post a signed DELIVER to /r/kibble (requires identity + passphrase)",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="schedule mode: dry-run + signed snapshot, no posting (same as default, for cron)",
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
        help="path to passphrase file (one line, stripped). Overrides KIBBLE_PASSPHRASE env var.",
    )
    parser.add_argument(
        "--no-sign",
        action="store_true",
        help="skip signing (unsigned snapshot only, for debugging without identity)",
    )
    args = parser.parse_args(argv)

    # Interactive launcher: when no flags given, show menu and prompt for a sub-tool.
    # This is the "what do you want to do" prompt you asked for.
    if len(sys.argv) == 1 and not (args.dry_run or args.publish or args.schedule):
        print("=" * 70)
        print("kibble-verifier — what do you want to do?")
        print("=" * 70)
        print("  1. kibble analysis (dry-run)   — fetch /r/kibble/export, compute stats, write signed snapshot")
        print("  2. kibble analysis + publish   — same, but also post signed CLAIM+DELIVER to /r/kibble")
        print("  3. quit")
        print("-" * 70)
        try:
            choice = input("choice> ").strip()
        except EOFError:
            print("no input, exiting")
            return 0
        if choice == "1":
            args.dry_run = True
        elif choice == "2":
            args.publish = True
        elif choice == "3":
            return 0
        else:
            print(f"unknown choice: {choice!r}, exiting")
            return 1

    # --dry-run is the default if neither --publish nor --schedule is set
    do_publish = args.publish
    do_schedule = args.schedule
    do_dry_run = args.dry_run or not do_publish

    start = time.time()
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # --- Load passphrase ---
    passphrase: bytearray | None = None
    if args.passphrase_file:
        passphrase = load_passphrase_from_file(args.passphrase_file)
        if passphrase is None:
            print(
                f"[{run_ts}] ERROR: passphrase file not found: {args.passphrase_file}",
                file=sys.stderr,
            )
            return 1
    elif "KIBBLE_PASSPHRASE" in os.environ:
        passphrase = load_passphrase_from_env()
        if passphrase is None:
            print(
                f"[{run_ts}] ERROR: KIBBLE_PASSPHRASE env var set but empty",
                file=sys.stderr,
            )
            return 1
    else:
        print(
            f"[{run_ts}] WARNING: no passphrase supplied (KIBBLE_PASSPHRASE or --passphrase-file). "
            f"Snapshot will be unsigned.",
            file=sys.stderr,
        )

    try:
        # --- Fetch + analyze ---
        print(f"[{run_ts}] fetching /r/kibble/export ...", file=sys.stderr)
        rows = fetch_export()
        fetch_duration = time.time() - start
        print(f"[{run_ts}] {len(rows)} lines read in {fetch_duration:.2f}s", file=sys.stderr)

        stats = analyze(rows)

        # --- Sign ---
        did: str | None = None
        snap_hash: str | None = None
        sig_b64: str | None = None
        key: ed25519.Ed25519PrivateKey | None = None

        if passphrase and not args.no_sign:
            try:
                key = load_identity(args.identity, passphrase)
                did, snap_hash, sig_b64 = sign_snapshot(key, stats)
                print(
                    f"[{run_ts}] identity loaded, did={did}, snapshot_hash={snap_hash[:16]}...",
                    file=sys.stderr,
                )
            except Exception as e:
                print(
                    f"[{run_ts}] WARNING: signing failed ({e}). Snapshot will be unsigned.",
                    file=sys.stderr,
                )
                did = None
                snap_hash = compute_snapshot_hash(stats)
                sig_b64 = None
        else:
            snap_hash = compute_snapshot_hash(stats)
            print(
                f"[{run_ts}] unsigned run, snapshot_hash={snap_hash[:16]}...",
                file=sys.stderr,
            )

        # --- Write signed snapshot ---
        snapshot_path = write_signed_snapshot(
            stats=stats,
            did=did or "unknown",
            snap_hash=snap_hash,
            sig_b64=sig_b64 or "",
            run_ts=run_ts,
            duration_s=fetch_duration,
            out_dir=SNAPSHOT_DIR,
        )
        print(f"[{run_ts}] snapshot written: {snapshot_path}", file=sys.stderr)

        # --- Publish (signed DELIVER to /r/kibble) ---
        if do_publish and did and sig_b64 and key:
            import secrets
            nonce = str(secrets.randbelow(10**18))
            claim_text = f"CLAIM v1 | kibble-verifier-run-{run_ts} | worker"
            deliver_text = build_deliver_text(stats, run_ts, snap_hash or "")

            print(f"[{run_ts}] posting signed CLAIM + DELIVER to /r/kibble ...", file=sys.stderr)

            # Sign the claim text
            claim_hash = hashlib.sha256(
                claim_text.encode("utf-8")
            ).digest()
            claim_sig = key.sign(claim_hash)
            claim_sig_b64 = base64.urlsafe_b64encode(claim_sig).rstrip(b"=").decode("ascii")

            claim_result = say_signed_in_room(did, claim_sig_b64, nonce, claim_text)
            print(f"[{run_ts}] CLAIM posted: {claim_result}", file=sys.stderr)

            deliver_result = say_signed_in_room(did, sig_b64, nonce, deliver_text)
            print(f"[{run_ts}] DELIVER posted: {deliver_result}", file=sys.stderr)

            summary = {
                "run_ts": run_ts,
                "did": did,
                "snapshot_hash": snap_hash,
                "signature": sig_b64,
                "export_lines": stats["export_lines"],
                "fetch_duration_s": round(fetch_duration, 2),
                "stats": stats,
                "snapshot_file": str(snapshot_path),
                "claim_post": claim_result,
                "deliver_post": deliver_result,
                "published": True,
            }
        else:
            summary = {
                "run_ts": run_ts,
                "did": did,
                "snapshot_hash": snap_hash,
                "signature": sig_b64,
                "export_lines": stats["export_lines"],
                "fetch_duration_s": round(fetch_duration, 2),
                "stats": stats,
                "snapshot_file": str(snapshot_path),
                "published": False,
                "note": "dry-run / schedule mode — snapshot written but not posted to /r/kibble",
            }

        print(json.dumps(summary, indent=2))

        return 0

    finally:
        # --- Zero passphrase in memory ---
        zero_passphrase(passphrase)
        # Also clear the env var so it's not linger in os.environ
        os.environ.pop("KIBBLE_PASSPHRASE", None)


if __name__ == "__main__":
    sys.exit(main())
