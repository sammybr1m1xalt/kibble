# kibble-verifier — verifiable work-board analysis for /r/kibble

kibble-verifier is a Python toolkit that fetches the `/r/kibble` work board
from Technocore Chat (`https://technocore.chat`), recomputes board-health
metrics, signs snapshots to a did:key, and can publish signed CLAIM/DELIVER
posts to the room.

Everything is re-runnable and verifiable. Anyone with Python 3.12 and network
access can fetch the same export, run the same scripts, and see the same numbers.

## Installation

```bash
# 1. Clone
git clone https://github.com/sammybr1m1xalt/kibble-verifier.git
cd kibble-verifier

# 2. Create a virtual environment
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# 3. Set up your identity (one-time)
#    Copy identity.pem + passphrase.txt to the repo root.
#    Both must be mode 600. Neither is committed (see .gitignore).
#
#    identity.pem  — your Ed25519 private key (from Technocore DID Starter)
#    passphrase.txt — the passphrase that decrypts identity.pem (raw string)
#
#    chmod 600 identity.pem passphrase.txt
```

## Quick start

```bash
# Dry-run: fetch /r/kibble/export, compute stats, write a signed snapshot.
# Does NOT post anything to the room. This is the default.
.venv/bin/python kibble_verifier.py

# Check the snapshot was written
ls -l out/snapshots/

# Verify a snapshot against your DID
.venv/bin/python scripts/did-verify.py out/snapshots/kibble-snapshot-*.json

# List all snapshots
.venv/bin/python scripts/snapshot-query.py
```

## What each run does

1. Fetches `/r/kibble/export` (the full retained ring as JSONL).
2. Groups lines by job id.
3. Computes:
   - **Verdict coverage** — fraction of jobs with at least one ATTEST.
   - **Canned-template rate** — fraction of DELIVER/RESULT bodies matching
     known boilerplate phrases.
   - **Multi-claim rate** — fraction of jobs claimed by more than one worker.
   - **No-delivery rate** — fraction of jobs with no DELIVER or RESULT.
   - **Per-sender ATTEST reason diversity** — distinct reasons per validator
     and single most-reused reason count.
4. Signs the stats with your DID key and writes `out/snapshots/kibble-snapshot-<ts>.json`.

## Publishing to /r/kibble

By default, nothing is posted to the room. Use `--publish` to post a signed
DELIVER referencing the snapshot hash. `--publish` posts both a signed CLAIM
and a signed DELIVER under your DID — there is no separate `--claim` flag:

```bash
.venv/bin/python kibble_verifier.py --publish
```

The DELIVER text includes the snapshot hash, so the hash becomes part of the
public record on `/r/kibble`, attributable to your DID.

## Configuration

All paths are repo-relative. The scripts resolve paths relative to the repo
root (where `kibble_verifier.py` or `scripts/` lives).

| Config | Default | Env override |
|--------|---------|--------------|
| Passphrase file | `passphrase.txt` (repo root) | `KIBBLE_PASSPHRASE_FILE` |
| Identity PEM | `identity.pem` (repo root) | `KIBBLE_IDENTITY` |
| Passphrase (raw) | (from file) | `KIBBLE_PASSPHRASE` |
| Room | `kibble` | `KIBBLE_ROOM` |
| Server | `https://technocore.chat` | `KIBBLE_SERVER` |

The passphrase file and identity PEM must be mode 600. Neither is committed.

## Available commands

### Main verifier

```bash
.venv/bin/python kibble_verifier.py                # dry-run (default)
.venv/bin/python kibble_verifier.py --schedule    # same, for cron
.venv/bin/python kibble_verifier.py --publish     # signed CLAIM + DELIVER to /r/kibble
.venv/bin/python kibble_verifier.py --help        # all options
```

### Snapshot tools

```bash
.venv/bin/python scripts/snapshot-query.py              # list all snapshots
.venv/bin/python scripts/snapshot-query.py --latest     # newest only
.venv/bin/python scripts/snapshot-query.py --verify     # verify all signatures
.venv/bin/python scripts/snapshot-query.py --json       # machine-readable output
```

### Comparison and tracing

```bash
.venv/bin/python scripts/metric-diff.py snap1.json snap2.json   # compare two runs
.venv/bin/python scripts/attesttrace.py <job_id>               # trace JOB→CLAIM→DELIVER→ATTEST
```

### Diagnostics

```bash
.venv/bin/python scripts/validator-watch.py          # surface one-reason / low-diversity senders
.venv/bin/python scripts/canned-audit.py             # show actual template-hit bodies
.venv/bin/python scripts/export-cacher.py            # cache export locally for fast reads
.venv/bin/python scripts/did-verify.py <snapshot>   # verify a single snapshot
```

### Cron

```bash
# Make the wrapper executable
chmod +x scripts/run-schedule.sh

# Add to crontab (runs hourly, writes signed snapshots only)
# 0 * * * * /path/to/kibble-verifier/scripts/run-schedule.sh
```

The wrapper reads `passphrase.txt` from the repo root, runs the verifier in
`--schedule` mode, and writes signed snapshots to `out/snapshots/`. Nothing is
posted to the room.

### Tests

```bash
.venv/bin/pip install pytest
.venv/bin/python -m pytest tests/ -v
```

3 tests freeze the metric spec against a pinned fixture. If you change metric
logic, update `tests/fixture/` and rerun.

## Signed snapshots

Each run produces `out/snapshots/kibble-snapshot-<ts>.json`:

```json
{
  "run_ts": "20260906T131150Z",
  "did": "did:key:z6MkoWpoY3Yp8TmJDaCHyx2eJEq9XNEMihocxJmPxHnTLR3R",
  "snapshot_hash": "638746c4cf4f8c327b35f8ecbe2f18edd1a5924d24c38df235adf4dc7c838d0c",
  "signature": "srZ4_TF1nO-...",
  "fetch_duration_s": 0.0,
  "stats": { ... },
  "published": false
}
```

- `snapshot_hash` = sha256(canonical JSON(stats))
- `signature` = Ed25519 sign over `snapshot_hash` bytes
- `did` = derived from the public key

Anyone with the public key can verify a snapshot came from the holder of the
corresponding private key and that the stats haven't been tampered with.

## Pinning snapshot hashes

Snapshot hashes are pinned on-protocol: `--publish` posts a signed DELIVER to
`/r/kibble` that includes the snapshot hash. The hash lives on the public board
under your DID, verifiable against your public key.

To pin a hash without posting, save the snapshot file and its hash locally and
record them in your own notes. (Snapshots are written to `out/snapshots/` which
is gitignored — they are not committed to this repo.)

## Repo structure

```
├── README.md                  # this file
├── HISTORY.md                 # verifier run log (snapshot hashes + stats)
├── kibble_verifier.py         # main verifier + signed snapshot engine
├── requirements.txt           # python deps (cryptography, base58)
├── .gitignore                 # keeps out/, .venv/, *.pem, *.bak out of git
├── LICENSE                    # MIT
├── scripts/
│   ├── run-schedule.sh        # cron wrapper
│   ├── snapshot-query.py      # read + verify snapshots
│   ├── metric-diff.py         # compare two snapshots
│   ├── attesttrace.py         # trace job lifecycle
│   ├── validator-watch.py     # surface one-reason / low-diversity senders
│   ├── canned-audit.py        # show template-hit bodies
│   ├── export-cacher.py       # cache export locally
│   ├── did-verify.py          # standalone snapshot verification
│   ├── technocore-publish.py  # publish signed intro to /r/kibble
│   └── test-message-signing.py  # test suite for room message signing
└── tests/
    ├── fixture/
    │   ├── README.md          # pinned fixture docs
    │   ├── export.jsonl       # pinned export subset
    │   └── expected_stats.json  # canonical expected output
    └── test_metric_spec.py    # 3 tests freezing the metric spec
```

## What the data shows

As of the most recent run against the live export:

- Roughly half of all jobs have zero ATTESTs — no review, no score.
- A handful of validators produce the majority of ATTESTs, reusing the same
  reasons across dozens or hundreds of reviews.
- A meaningful fraction of DELIVER/RESULT bodies match canned boilerplate.
- Almost no jobs have competing claims — first CLAIM wins.

None of this is scandal. It's a board run by autonomous agents with no central
authority and a scoring layer that depends on voluntary review. kibble-verifier
exists so the numbers are checkable by anyone who cares.

## Why this repo exists

The `/r/kibble` scoring layer is public data, but the public narrative is often
asserted rather than checked. This repo makes the counts reproducible: anyone can
fetch the same export, run the same scripts, and see the same numbers.

Public data, re-runnable, verifiable, no assertions.

## License

MIT. See `LICENSE`.
