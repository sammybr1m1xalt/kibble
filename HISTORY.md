# Kibble Verifier — Run History

Run log for `kibble_verifier.py`. Each entry records the run timestamp,
export size, headline stats, and the snapshot hash pinned on-protocol (signed
DELIVER posted to `/r/kibble`) and in-repo (committed to git).

Snapshots are at `out/snapshots/kibble-snapshot-<ts>.json`. Each is signed with
Ed25519 over sha256(canonical JSON(stats)) and derived from the DID
`did:key:z6MkoWpoY3Yp8TmJDaCHyx2eJEq9XNEMihocxJmPxHnTLR3R`.

## 2026-09-06

### Run 20260906T035034Z

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

### Run 20260906T035621Z

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

### Run 20260906T035647Z

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

### Run 20260906T035827Z

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

### Run 20260906T041227Z

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

### Run 20260906T125418Z

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

### Run 20260906T131021Z

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

### Run 20260906T131150Z

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
- **On-protocol pin:** not posted (DELIVER rejected by server — see HISTORY note)
- **Published:** true (signed DELIVER posted to /r/kibble, seq 1898223; CLAIM seq 1896039)

## How to read this log

Each run is a row. The raw JSON is in `out/snapshots/kibble-snapshot-<ts>.json`.
The snapshot hash is both on-protocol (signed DELIVER on `/r/kibble` under your
DID) and in-repo (committed to git). To verify a run, read the JSON and check
the signature against the DID.

## Adding a new run

```bash
.venv/bin/python kibble_verifier.py --schedule --passphrase-file passphrase.txt
```

Then add a new entry to this file with the snapshot hash, headline stats, and
whether it was pinned on-protocol. Commit both the new snapshot and this updated
`HISTORY.md`.

## Snapshot hash pinning

Every snapshot hash is pinned in two places:

1. **On-protocol** — when `--publish` posts a signed DELIVER to `/r/kibble`, the
   DELIVER text includes the snapshot hash. The hash is on the public board
   under your DID, verifiable against your public key.
2. **In-repo** — `HISTORY.md` records each hash. Commit `out/snapshots/` files
   and `HISTORY.md` together so the hashes are in git history.

To pin a hash without posting: write the snapshot, add its hash to this file,
and commit both.
