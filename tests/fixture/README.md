# Pinned fixture for kibble-verifier metric spec

This directory holds a small, stable export snapshot used to freeze the metric
spec. `export.jsonl` is a trimmed real export (selected lines covering every
line type and edge case). `expected_stats.json` is the canonical output of
`analyze()` against that fixture, computed by hand / by a trusted run.

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

```bash
# Make sure kibble_verifier.py is on PYTHONPATH or in the same dir
python3 -c "
import json, sys
sys.path.insert(0, '.')
from kibble_verifier import fetch_fixture, analyze
rows = fetch_fixture()
stats = analyze(rows)
print(json.dumps(stats, indent=2))
" > expected_stats.json
```

Then review the diff and commit.

## Fixture contents

The fixture is a subset of a real `/r/kibble/export` run. It includes:

- Multiple JOB lines with different job ids
- CLAIM lines (some jobs claimed once, some claimed multiple times)
- DELIVER/RESULT lines (some matching canned phrases, some not)
- ATTEST lines (multiple senders, some reusing the same reason, some diverse)
- Edge cases: empty bodies, lines that don't parse as JSON, unknown prefixes

The exact lines are preserved from the export snapshot they were drawn from.
Don't edit them by hand — re-extract from a real export if you need to refresh.
