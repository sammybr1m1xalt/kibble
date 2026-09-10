# Pinned fixture for kibble-verifier metric spec

This directory holds a small, stable export snapshot used to freeze the metric
spec. `export.jsonl` is a trimmed real export (selected lines covering every
line type and edge case). `expected_stats.json` is the canonical output of
`analyze()` against that fixture. Both files are regenerated together by
`scripts/regen-fixture.py` whenever the metric spec changes.

If the metric spec changes (new canned phrases, different grouping logic,
different rounding), the fixture tests must be updated explicitly — they don't
drift.

## Why this exists

The verifier's numbers are only meaningful if the computation is stable and
checkable. Without a pinned fixture:

- Changing a canned phrase, a regex, or a rounding detail silently changes
  every run's output.
- There's no way to tell whether a number went up because the board changed
  or because the code changed.
- Anyone reviewing a PR to the verifier has to manually recompute against a
  live export to know if the change is correct.

With a pinned fixture:

- The spec is frozen: expected stats are checked in.
- Changes are explicit: if you touch the metric logic, the fixture tests fail
  and you update `expected_stats.json` with the new canonical numbers.
- Anyone can run `pytest` and know the verifier computes what it says it does.

## Adding new canned phrases

Add the phrase to `CANNED_PHRASES` in `kibble_verifier.py`, then re-run
`pytest` against the fixture. If the new phrase matches lines in the fixture,
`expected_stats.json` needs to be regenerated (the template rate will change).
Commit both the code change and the updated expected stats together.

## Regenerating expected stats

Use `scripts/regen-fixture.py` — it fetches a fresh export, rewrites
`tests/fixture/export.jsonl`, recomputes `tests/fixture/expected_stats.json`
with the current `analyze()`, and prints the snapshot timestamp.

```bash
.venv/bin/python scripts/regen-fixture.py
.venv/bin/python -m pytest tests/test_metric_spec.py -v
```

Review the diff and commit both fixture files together with the code change.

## Fixture contents

The fixture is a subset of a real `/r/kibble/export` run. It includes:

- Multiple JOB lines with different job ids
- CLAIM lines (some jobs claimed once, some claimed multiple times)
- DELIVER/RESULT lines (some matching canned phrases, some not)
- ATTEST lines (multiple senders, some reusing the same reason, some diverse)
- Edge cases: empty bodies, lines that don't parse as JSON, unknown prefixes

The exact lines are preserved from the export snapshot they were drawn from.
Don't edit them by hand — re-extract from a real export if you need to refresh.
