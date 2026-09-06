"""Fixtures and tests for the kibble-verifier metric spec.

The fixture is a small, stable export snapshot. Tests assert that
kibble_verifier.py's analyze() produces exactly the expected stats
against that fixture. If the metric spec changes, regenerate
expected_stats.json and commit both together.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).resolve().parent / "fixture"
EXPORT_PATH = FIXTURE_DIR / "export.jsonl"
EXPECTED_PATH = FIXTURE_DIR / "expected_stats.json"


def _load_fixture() -> list[dict]:
    """Load the pinned fixture export lines."""
    rows: list[dict] = []
    for line in EXPORT_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _load_expected() -> dict:
    """Load the canonical expected stats for the fixture."""
    return json.loads(EXPECTED_PATH.read_text())


@pytest.fixture
def fixture_rows() -> list[dict]:
    """The pinned export fixture."""
    return _load_fixture()


@pytest.fixture
def expected_stats() -> dict:
    """The canonical expected stats for the fixture."""
    return _load_expected()


def test_fixture_has_content(fixture_rows: list[dict]) -> None:
    """The fixture is non-empty and contains all line types."""
    assert len(fixture_rows) >= 10, "fixture is too small to be useful"
    texts = [r.get("text", "") for r in fixture_rows]
    assert any(t.startswith("JOB ") for t in texts), "no JOB lines in fixture"
    assert any(t.startswith("CLAIM ") for t in texts), "no CLAIM lines in fixture"
    assert any(t.startswith("DELIVER ") or t.startswith("RESULT ") for t in texts), (
        "no DELIVER/RESULT lines in fixture"
    )
    assert any(t.startswith("ATTEST ") for t in texts), "no ATTEST lines in fixture"


def test_analyze_produces_expected_stats(fixture_rows: list[dict], expected_stats: dict) -> None:
    """analyze() against the fixture produces exactly the expected stats."""
    # Import here so the test doesn't break if kibble_verifier isn't installed
    from kibble_verifier import analyze

    stats = analyze(fixture_rows)
    # Drop run-specific fields that change between runs
    for key in ("export_lines",):
        assert stats[key] == expected_stats[key], (
            f"{key}: got {stats[key]}, expected {expected_stats[key]}"
        )
    # The rest of the metric spec must match exactly
    for key in (
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
    ):
        assert stats[key] == expected_stats[key], (
            f"{key}: got {stats[key]}, expected {expected_stats[key]}"
        )

    # sender_reuse_table is sorted and capped; check the first N entries
    expected_table = expected_stats["sender_reuse_table"]
    got_table = stats["sender_reuse_table"]
    assert len(got_table) == len(expected_table), (
        f"sender_reuse_table length: got {len(got_table)}, expected {len(expected_table)}"
    )
    for got, exp in zip(got_table, expected_table):
        for key in (
            "sender",
            "total_attests",
            "distinct_reasons",
            "max_single_reason_count",
            "max_reuse_ratio",
        ):
            assert got[key] == exp[key], (
                f"sender_reuse_table[{key}]: got {got[key]}, expected {exp[key]}"
            )


def test_canned_phrases_in_code_match_fixture() -> None:
    """The CANNED_PHRASES in kibble_verifier.py are the same ones used to
    compute the expected stats. If you add a phrase, regenerate the fixture
    expected stats."""
    from kibble_verifier import CANNED_PHRASES

    expected_phrases = _load_expected().get("canned_phrases", [])
    assert CANNED_PHRASES == expected_phrases, (
        f"CANNED_PHRASES drift: code has {CANNED_PHRASES!r}, "
        f"expected stats has {expected_phrases!r}. "
        "Regenerate expected_stats.json after changing CANNED_PHRASES."
    )
