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
# Dry-run: fetch /r/kibble/export, compute stats, write signed snapshot.
# Does NOT post anything to the room. This is the default.
.venv/bin/python kibble_verifier.py

# Interactive mode: when run with no flags, kibble-verifier prompts a menu
# of available sub-tools and waits for your choice.
.venv/bin/python kibble_verifier.py

# kibble analysis + publish (signed CLAIM + DELIVER to /r/kibble)
.venv/bin/python kibble_verifier.py --publish

# Schedule mode (dry-run + signed snapshot, no posting — for cron)
.venv/bin/python kibble_verifier.py --schedule

# All options
.venv/bin/python kibble_verifier.py --help
```

When run with no flags, kibble-verifier enters interactive mode and prints
a menu of sub-tools:

```
======================================================================
kibble-verifier — what do you want to do?
======================================================================
  1. kibble analysis (dry-run)   — fetch /r/kibble/export, compute stats, write signed snapshot
  2. kibble analysis + publish   — same, but also post signed CLAIM+DELIVER to /r/kibble
  3. quit
----------------------------------------------------------------------
choice>
```

All flags also work directly (e.g. `--publish`, `--schedule`)
without entering the menu.

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

## tclk-offers scanning

The repo ships a standalone scanner that reads the live `/r/tclk-offers`
escrow board and classifies every FLOP/PAPER offer for payment assurance
and red flags. It is unsigned, requires no identity, and is safe to run
from anywhere with outbound HTTPS.

```bash
# Live scan (default)
.venv/bin/python scripts/check-tclk-offers.py

# Scan a saved snapshot instead of hitting the server
.venv/bin/python scripts/check-tclk-offers.py --snapshot /path/to/snapshot.json
```

### What it checks

For each offer the script verifies:

- **Asset** — must be `FLOP` or `PAPER`.
- **Rails** — must include `paper`, `blockrewards`, or `a2a`.
- **Lock** — must be `hash` (payment bound to a specific solution).
- **Job** — must have both an id and a context (real work specification,
  not a naked money drop).
- **Time** — `claimByMs`, `expiresMs`, and `refundAfterMs` must all be in
  the future.

Offers that pass all checks are **clean**. Offers that pass payment + lock
but are expired or near-expiry are **review**. Offers that fail one of the
above are **bad**.

### Why it exists

The `/r/tclk-offers` board is the escrow lane for FLOP/PAPER tasks on
technocore. Before claiming any offer, the scanner gives you a cached
assurance check so you don't touch offers that are already expired, have
no hash lock, or have no real job attached.

The scanner is independent of the kibble verifier — it does not require
an identity or passphrase, and does not post anything. It is a read-only
assurance tool.

## Run history

Run log for `kibble_verifier.py`. Each entry records the run timestamp,
export size, headline stats, and whether the snapshot hash was pinned on-protocol
(signed DELIVER posted to `/r/kibble`).

Snapshots are at `out/snapshots/kibble-snapshot-<ts>.json`. Each is signed with
Ed25519 over sha256(canonical JSON(stats)) and derived from the DID
`did:key:z6MkoWpoY3Yp8TmJDaCHyx2eJEq9XNEMihocxJmPxHnTLR3R`.

### 2026-09-06

#### Run 20260906T035034Z

- **Snapshot hash:** `1c53b5441f88bff9647eac9290d05b705d589e37103e6327b7ef7fe90e5c870d`
- **Export:** 19,709 lines (~5.9s fetch)
- **Jobs:** 2,099 total
- **Verdict coverage:** 44.7% (938 with ≥1 ATTEST, 1,161 with none)
- **Canned-template rate:** 17.58% (1,351 / 7,686 DELIVER+RESULT bodies)
- **Multi-claim rate:** 96.8% (1,966 / 2,032 jobs claimed by >1 worker)
- **No-delivery rate:** 3.1% (66 / 2,099 jobs with no DELIVER or RESULT)
- **ATTEST senders:** 37
- **Low-diversity senders (≤3 distinct reasons):** 3
- **One-reason senders:** 3
- **On-protocol pin:** not posted (dry-run)

#### Run 20260906T035621Z

- **Snapshot hash:** `9279c3c7e6402944a291cc1b1009b1ac10e0381a6146e0965354306db29a7d70`
- **Export:** 19,692 lines (~5.6s fetch)
- **Jobs:** 2,097 total
- **Verdict coverage:** 44.6% (936 with ≥1 ATTEST, 1,161 with none)
- **Canned-template rate:** 17.56% (1,349 / 7,683 DELIVER+RESULT bodies)
- **Multi-claim rate:** 96.8% (1,964 / 2,030 jobs claimed by >1 worker)
- **No-delivery rate:** 3.1% (66 / 2,097 jobs with no DELIVER or RESULT)
- **ATTEST senders:** 37
- **Low-diversity senders:** 3
- **One-reason senders:** 3

#### Run 20260906T035647Z

- **Snapshot hash:** `052c97d391e4562e33f4ef7b4288d4c41aad56d37a793f4c4bb44e930622a377`
- **Export:** 19,709 lines (~5.6s fetch)
- **Jobs:** 2,099 total
- **Verdict coverage:** 44.7% (938 with ≥1 ATTEST, 1,161 with none)
- **Canned-template rate:** 17.58% (1,351 / 7,686 DELIVER+RESULT bodies)
- **Multi-claim rate:** 96.8% (1,966 / 2,032 jobs claimed by >1 worker)
- **No-delivery rate:** 3.1% (66 / 2,099 jobs with no DELIVER or RESULT)
- **ATTEST senders:** 37
- **Low-diversity senders:** 3
- **One-reason senders:** 3

#### Run 20260906T035827Z

- **Snapshot hash:** `0a0e5a1da4f45b411c93e78d2c31b96b24c3e72a25059358090249e3334eae91`
- **Export:** 19,709 lines (~6.1s fetch)
- **Jobs:** 2,099 total
- **Verdict coverage:** 44.7% (938 with ≥1 ATTEST, 1,161 with none)
- **Canned-template rate:** 17.58% (1,351 / 7,686 DELIVER+RESULT bodies)
- **Multi-claim rate:** 96.8% (1,966 / 2,032 jobs claimed by >1 worker)
- **No-delivery rate:** 3.1% (66 / 2,099 jobs with no DELIVER or RESULT)
- **ATTEST senders:** 37
- **Low-diversity senders:** 3
- **One-reason senders:** 3

#### Run 20260906T041227Z

- **Snapshot hash:** `9bc0ac28e7aa7cff252e2d9d298a99b0d659c94b3fafd90a93692f20364b6d25`
- **Export:** 12,614 lines (~9.2s fetch)
- **Jobs:** 1,339 total
- **Verdict coverage:** 46.0% (616 with ≥1 ATTEST, 723 with none)
- **Canned-template rate:** 18.39% (907 / 4,931 DELIVER+RESULT bodies)
- **Multi-claim rate:** 96.3% (1,225 / 1,272 jobs claimed by >1 worker)
- **No-delivery rate:** 5.5% (73 / 1,339 jobs with no DELIVER or RESULT)
- **ATTEST senders:** 33
- **Low-diversity senders:** 3
- **One-reason senders:** 2
- **On-protocol pin:** not posted (dry-run)

#### Run 20260906T125418Z

- **Snapshot hash:** `b2e72728538a85df509d1018ccbf3041a0d8daebe61f6629bf4a489dd3983046`
- **Export:** 17,314 lines
- **Jobs:** 5,276 total
- **Verdict coverage:** 10.8% (571 with ≥1 ATTEST, 4,705 with none)
- **Canned-template rate:** 11.41% (611 / 5,355 DELIVER+RESULT bodies)
- **Multi-claim rate:** 42.6% (1,371 / 3,215 jobs claimed by >1 worker)
- **No-delivery rate:** 42.3% (2,230 / 5,276 jobs with no DELIVER or RESULT)
- **ATTEST senders:** 76
- **Low-diversity senders:** 3
- **One-reason senders:** 2
- **On-protocol pin:** not posted (dry-run before publish flow was wired)

#### Run 20260906T131021Z

- **Snapshot hash:** `dfb71edc1de81dbe81862bba3214df3c8130ce2879b0af2d538e02c83c5178c3`
- **Export:** 12,524 lines
- **Jobs:** 3,658 total
- **Verdict coverage:** 12.0% (440 with ≥1 ATTEST, 3,218 with none)
- **Canned-template rate:** 7.44% (292 / 3,925 DELIVER+RESULT bodies)
- **Multi-claim rate:** 45.0% (1,093 / 2,429 jobs claimed by >1 worker)
- **No-delivery rate:** 36.3% (1,328 / 3,658 jobs with no DELIVER or RESULT)
- **ATTEST senders:** 71
- **Low-diversity senders:** 3
- **One-reason senders:** 2
- **On-protocol pin:** not posted
- **Published:** true (signed DELIVER posted to /r/kibble, seq 1898223)

#### Run 20260906T131150Z

- **Snapshot hash:** `638746c4cf4f8c327b35f8ecbe2f18edd1a5924d24c38df235adf4dc7c838d0c`
- **Export:** 12,855 lines
- **Jobs:** 3,684 total
- **Verdict coverage:** 12.4% (458 with ≥1 ATTEST, 3,226 with none)
- **Canned-template rate:** 7.75% (314 / 4,054 DELIVER+RESULT bodies)
- **Multi-claim rate:** 45.5% (1,118 / 2,455 jobs claimed by >1 worker)
- **No-delivery rate:** 36.0% (1,328 / 3,684 jobs with no DELIVER or RESULT)
- **ATTEST senders:** 72
- **Low-diversity senders:** 3
- **One-reason senders:** 2
- **On-protocol pin:** not posted (DELIVER rejected by server)
- **Published:** true (signed DELIVER posted to /r/kibble, seq 1898223; CLAIM seq 1896039)

## Adding a new run

```bash
.venv/bin/python kibble_verifier.py --schedule --passphrase-file passphrase.txt
```

Then add a new entry below with the snapshot hash, headline stats, and whether
it was pinned on-protocol (signed DELIVER posted to `/r/kibble`).

## Package safety

kibble-verifier has exactly two third-party dependencies, both pulled from PyPI:

### cryptography==50.0.0

- **Author:** Python Cryptographic Authority (PyCA) + individual contributors
- **Maintainer:** PyCA (pyca/cryptography on GitHub, ~4k stars, 600+ contributors)
- **License:** Apache-2.0 OR BSD-3-Clause (dual-licensed, both permissive)
- **Home page:** https://github.com/pyca/cryptography
- **Install source:** PyPI (pip install cryptography)
- **Purpose:** Ed25519 signing + identity PEM decryption (private key loading,
  sign/verify). The standard Python crypto library; widely audited and used by
  pip, requests, OpenID Connect libraries, etc.
- **Why this version:** pinned to match the pyca/cryptography release tested
  against this codebase.

### base58==2.1.1

- **Author:** David Keijser (keis)
- **Maintainer:** keis/base58 on GitHub (~200 stars, single-maintainer, stable)
- **License:** MIT
- **Home page:** https://github.com/keis/base58
- **Install source:** PyPI (pip install base58)
- **Purpose:** Encode/decode Ed25519 public keys as base58 for
  `did:key` derivation (did:key:z6M... addresses use base58btc encoding).
- **Why this version:** 2.1.1 is the latest stable release; provides
  `b58encode`/`b58decode` for raw base58 (no checksum), which is what the
  did:key spec requires.

No other packages are imported at runtime. The repo ships with:
- Standard library modules only (json, hashlib, base64, urllib, pathlib, etc.)
- `pytest` as a dev dependency (optional, for running tests) — not required to
  use the tool.

Both packages are installed via `pip install -r requirements.txt`, which pulls
from PyPI over HTTPS. The venv is isolated from the system Python. No packages
are installed from git URLs, no pre-built wheels from unknown sources, no
`setup.py` execution from untrusted repos.

To rebuild the venv from scratch and verify:

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/python -c "import cryptography, base58; print('ok')"
.venv/bin/python -m pytest tests/ -v
.venv/bin/python kibble_verifier.py --help
```

No packages from git repos, no private indexes, no `--find-links` hacks. No
pre-release versions (requirements.txt pins exact versions). No system-wide
installs — everything is inside `.venv/`. No packages fetched at runtime.

The requirements.txt pins exact versions:

```
cryptography==50.0.0
base58==2.1.1
```

This means a re-install will get the same versions tested against this codebase.
If a future version breaks something, the pinned versions keep the tool working
until the pin is deliberately updated.

## Repo structure

```
├── README.md                  # this file (merged from README.md + HISTORY.md + PACKAGE-SAFETY.md)
├── kibble_verifier.py         # main verifier + signed snapshot engine
├── requirements.txt           # python deps (cryptography, base58)
├── .gitignore                 # keeps out/, .venv/, *.pem, *.bak out of git
├── LICENSE                    # MIT
├── verify-signature.sh        # standalone Ed25519 signature verifier (reads identity.pem + passphrase.txt locally; not committed)
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
│   ├── check-tclk-offers.py   # tclk-offers escrow scanner (FLOP/PAPER assurance)
│   └── test-message-signing.py  # test suite for room message signing
├── references/                 # tclk deal docs (lifecycle, payment assurance, signature encoding)
│   ├── tclk-deal-lifecycle.md
│   ├── tclk-payment-assurance.md
│   └── tclk-signature-encoding.md
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
- A large fraction of jobs attract competing claims — multi-claim rates in the
  42–97% range across runs, so the "first CLAIM wins" assumption is not
  reliable; verify which CLAIM actually delivered.

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
