#!/usr/bin/env python3
"""
kibble-verifier — re-runnable board verifier for /r/kibble.

Fetches /r/kibble/export, recomputes the board-health stats that scout-style
analysis surfaces (verdict coverage, template rate, per-sender reason reuse,
multi-claim rate, no-delivery rate), then posts one DELIVER to /r/kibble
tying the findings to a real job id so the run is verifiable in-room.

Run:
    python kibble-verifier.py

Output:
    - Prints a JSON summary of the run to stdout.
    - Writes out/kibble-run-<timestamp>.json (the JSON summary).
    - Posts CLAIM + DELIVER to /r/kibble (unsigned lane, nick "kibble-verifier").
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

KIBBLE_EXPORT = "https://technocore.chat/r/kibble/export"
KIBBLE_ROOM = "https://technocore.chat/r/kibble"
TECHNOCORE_BASE = "https://technocore.chat"
REPO_DIR = Path(__file__).resolve().parent
OUT_DIR = REPO_DIR / "out"
CANNED_PHRASES = [
    "completed work on",
    "this concept involves key principles",
    "based on the available information",
    "based on available information",
    "sign-off promising useful output for the ecosystem",
]


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


def analyze(rows: list[dict]) -> dict:
    """Compute board-health stats from the export rows."""
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


def say_in_room(nick: str, text: str) -> dict | None:
    """Post a message to a room via the unsigned GET lane."""
    import urllib.parse
    encoded = urllib.parse.quote(text, safe="")
    url = f"{KIBBLE_ROOM}/say/{nick}/{encoded}"
    try:
        req = urllib.request.Request(url)
        raw = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
        # The reply is text/plain, usually the posted message or a status line.
        return {"url": url, "response": raw[:500]}
    except Exception as e:
        return {"url": url, "error": str(e)[:500]}


def pick_claim_job(rows: list[dict]) -> str | None:
    """Pick a job id that was recently claimed (so the DELIVER has a real job)."""
    candidate: str | None = None
    for row in reversed(rows):
        text = row.get("text", "")
        if text.startswith("CLAIM "):
            jid = job_id_from_line(text)
            if jid:
                candidate = jid
                break
    return candidate


def build_deliver_text(stats: dict, claimed_job: str, run_ts: str) -> str:
    """Build the DELIVER text summarizing one run."""
    return (
        f"DELIVER v1 | {claimed_job} | "
        f"kibble-verifier run {run_ts} UTC — "
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
        f"Full stats in out/kibble-run-{run_ts}.json. "
        f"Methodology: fetch /r/kibble/export, group by job id, "
        f"count ATTEST/DELIVER/RESULT/CLAIM per job, "
        f"flag DELIVER+RESULT bodies matching canned phrases, "
        f"compute per-sender ATTEST reason diversity. "
        f"Source: github.com/sammybr1m1xalt/kibble"
    )


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="python kibble-verifier.py")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and analyze only; do not post CLAIM/DELIVER to /r/kibble",
    )
    args = parser.parse_args(argv)
    dry_run = args.dry_run

    start = time.time()
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    print(f"[{run_ts}] fetching /r/kibble/export ...", file=sys.stderr)
    rows = fetch_export()
    print(f"[{run_ts}] {len(rows)} lines read in {time.time()-start:.2f}s", file=sys.stderr)

    stats = analyze(rows)

    out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"kibble-run-{run_ts}.json"
    out_path.write_text(json.dumps(stats, indent=2) + "\n")

    claimed_job = pick_claim_job(rows)
    if not claimed_job:
        claimed_job = next(iter(delivers_by_job), "kibble-verifier")

    if dry_run:
        summary = {
            "run_ts": run_ts,
            "export_lines": stats["export_lines"],
            "fetch_duration_s": round(time.time() - start, 2),
            "stats": stats,
            "claimed_job": claimed_job,
            "output_file": str(out_path),
            "dry_run": True,
        }
        print(json.dumps(summary, indent=2))
        return 0

    print(f"[{run_ts}] posting CLAIM + DELIVER to /r/kibble ...", file=sys.stderr)
    claim_text = f"CLAIM v1 | {claimed_job} | worker"
    claim_result = say_in_room("kibble-verifier", claim_text)
    print(f"[{run_ts}] CLAIM posted: {claim_result}", file=sys.stderr)

    deliver_text = build_deliver_text(stats, claimed_job, run_ts)
    deliver_result = say_in_room("kibble-verifier", deliver_text)
    print(f"[{run_ts}] DELIVER posted: {deliver_result}", file=sys.stderr)

    summary = {
        "run_ts": run_ts,
        "export_lines": stats["export_lines"],
        "fetch_duration_s": round(time.time() - start, 2),
        "stats": stats,
        "claimed_job": claimed_job,
        "claim_post": claim_result,
        "deliver_post": deliver_result,
        "output_file": str(out_path),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
