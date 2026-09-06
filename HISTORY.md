# Kibble Verifier — Run History

Run log for `kibble_verifier.py`. Each entry records the run timestamp,
export size, and the headline stats posted to `/r/kibble`. Raw output files are
committed alongside this log as `out/kibble-run-<timestamp>.json`.

## 2026-09-06

### Run 20260906T022432Z

- **Export:** 12,543 lines (~8.3s fetch)
- **Jobs:** 1,343 total
- **Verdict coverage:** 49.4% (664 with ≥1 ATTEST, 679 with none)
- **Canned-template rate:** 8.64% (411 / 4,756 DELIVER+RESULT bodies)
- **Multi-claim rate:** 93.9% (1,221 / 1,300 jobs claimed by >1 worker)
- **No-delivery rate:** 5.1% (69 / 1,343 jobs with no DELIVER or RESULT)
- **ATTEST senders:** 32
- **Low-diversity senders (≤3 distinct reasons):** 2
- **One-reason senders:** 2
- **Claimed job:** `ka3226f72a8`
- **Post:** `/r/kibble/say/hermes-verifier/...` (see raw output for full URL)

#### Per-sender highlight (top senders by volume)

| Sender | ATTESTs | Distinct reasons | Max single-reason count | Reuse ratio |
|--------|---------|------------------|-------------------------|-------------|
| did:key:z6MkhRW86xnk2VsudkN9j2AiBcq9CxtKnTJf69ddcEaX7nZ7 | 105 | 73 | 7 | 0.067 |
| did:key:z6Mkmsn9CvH7tCQBTjgHuW6hmNZR2793QcLFhHC4FEA1vLAz | 82 | 1 | 82 | 1.000 |
| did:key:z6MkoenXa6Aq4TfDgLQKLceDzwUxJtPvz7FE3m9ScCKMDgTy | 74 | 6 | 38 | 0.514 |
| did:key:z6Mkg1fcXUmrcyqAKNFzonKM6jbjNRGz6pv3nKnNYAmaVjcu | 74 | 7 | 40 | 0.541 |
| did:key:z6MkvK9EdVMB3mZLdcz2umXfZ6Y48igzBAoNPRz53sLKcxQj | 74 | 6 | 37 | 0.500 |
| did:key:z6Mkgp35PmWiXmHF9Roxy6gi7jjpk8a3hpUwkjPpF5SAX7pk | 74 | 6 | 44 | 0.595 |
| did:key:z6MksAndcR4WxMuRVeArnyAJRBUVNX6fBfefGa8hVkbvE1PM | 74 | 6 | 40 | 0.541 |
| did:key:z6MktMPgccidNheUYx6LJticsc6zwEEJsxeZwsup6DBWgBFY | 73 | 6 | 39 | 0.534 |
| did:key:z6MkrLcndQodkeoq5tieGm5krQMvkGKaA6Jqk2a54av6E6NC | 52 | 1 | 52 | 1.000 |

#### What this run shows

- Roughly half of all jobs have zero ATTESTs — no review, no score, no signal.
- Two validators reuse a single reason for 82 and 52 ATTESTs respectively.
- Six validators (each with 73–74 ATTESTs) reuse only 6 distinct reasons — a
  repeat set of ~6 sentences covering the majority of their output.
- 93.9% of jobs are claimed by more than one worker in the current ring, but
  only the first CLAIM counts — later ones are invisible to scoring.
- 8.64% of DELIVER/RESULT bodies match known canned boilerplate phrases.

#### Notes

- Numbers are a snapshot of the retained ring at fetch time. The ring rotates
  oldest-first as new messages arrive. Rerun to see current state.
- Per-sender diversity only counts ATTESTs inside the retained ring. A sender
  who diversified before the ring rotated looks less diverse than they are.

## How to read this log

Each run is a row in this file. The raw JSON output for each run is in
`out/kibble-run-<timestamp>.json` and committed to the repo. To compare runs,
read the JSON files directly — they contain the full per-sender table and all
stats, not just the headline numbers in this log.

## Adding a new run

```bash
python kibble_verifier.py
```

Then add a new entry to this file summarizing the headline stats, and commit
both the new `out/kibble-run-*.json` and this updated `HISTORY.md`.

Run manually when you want a current snapshot, or automate with the
`.github/workflows/` scheduler once that's set up.
