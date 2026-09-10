#!/usr/bin/env python3
"""
regen-fixture — regenerate the pinned metric-spec fixture + expected stats.

Usage:
    .venv/bin/python scripts/regen-fixture.py

This fetches a fresh /r/kibble/export, writes the first N lines to
tests/fixture/export.jsonl, recomputes the expected stats with
kibble_verifier.analyze(), and writes tests/fixture/expected_stats.json.

If you change CANNED_PHRASES, grouping logic, or rounding in
kibble_verifier.py, re-run this script so the fixture matches the new
code. Then run pytest — the three metric-spec tests should pass.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_DIR / "tests" / "fixture"
EXPORT_PATH = FIXTURE_DIR / "export.jsonl"
EXPECTED_PATH = FIXTURE_DIR / "expected_stats.json"

# Import from the repo root
sys.path.insert(0, str(REPO_DIR))
from kibble_verifier import fetch_export, analyze, CANNED_PHRASES


def main() -> int:
    print("Fetching /r/kibble/export ...")
    rows = fetch_export()
    print(f"  {len(rows)} lines fetched")

    # Write the pinned fixture (first N lines, capped so it stays small)
    N = 2000
    kept = rows[:N]
    if len(kept) < 10:
        print("ERROR: fixture too small after cap", file=sys.stderr)
        return 1
    EXPORT_PATH.write_text("\n".join(json.dumps(r) for r in kept) + "\n")
    print(f"  wrote {len(kept)} lines to {EXPORT_PATH}")

    # Recompute expected stats from the fixture
    stats = analyze(kept)
    expected = {
        "export_lines": stats["export_lines"],
        "job_count": stats["job_count"],
        "jobs_with_at_least_one_attest": stats["jobs_with_at_least_one_attest"],
        "jobs_with_no_verdict": stats["jobs_with_no_verdict"],
        "verdict_coverage_pct": stats["verdict_coverage_pct"],
        "deliver_result_count": stats["deliver_result_count"],
        "canned_template_hits": stats["canned_template_hits"],
        "canned_template_rate_pct": stats["canned_template_rate_pct"],
        "jobs_with_claims": stats["jobs_with_claims"],
        "multi_claim_job_count": stats["multi_claim_job_count"],
        "multi_claim_rate_pct": stats["multi_claim_rate_pct"],
        "jobs_with_delivery": stats["jobs_with_delivery"],
        "jobs_with_no_delivery": stats["jobs_with_no_delivery"],
        "no_delivery_rate_pct": stats["no_delivery_rate_pct"],
        "attest_count": stats["attest_count"],
        "attest_senders": stats["attest_senders"],
        "senders_with_low_diversity_reason_reuse": stats[
            "senders_with_low_diversity_reason_reuse"
        ],
        "senders_reusing_one_reason": stats["senders_reusing_one_reason"],
        "sender_reuse_table": stats["sender_reuse_table"],
        "canned_phrases": CANNED_PHRASES,
    }
    EXPECTED_PATH.write_text(json.dumps(expected, indent=2) + "\n")
    print(f"  wrote expected stats to {EXPECTED_PATH}")
    print(f"  snapshot: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} UTC")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
