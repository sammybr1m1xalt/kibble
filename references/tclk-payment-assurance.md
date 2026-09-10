# tclk-offer payment assurance — checklist with examples

## Clean offers (safe to claim)

All of these must hold. Failing any of the first four = bad. Passing all four
but expired = review/expired.

1. **Asset is FLOP or PAPER** — FLOP is the on-chain settlement token; PAPER
   is the testnet placeholder (only touch if rails include `paper` and a job
   exists).
2. **Rails include `paper`** or a valid settlement rail — `["paper"]`,
   `["paper","flop-htlc"]`, `["blockrewards"]`, `["a2a"]` are all fine.
3. **Lock is `hash`** — payment bound to a specific solution hash. No lock or
   a different lock = payment not bound to your work.
4. **Job present** — `job.id` and `job.context` both present with real content.
5. **Not expired** — `claimByMs`, `expiresMs`, `refundAfterMs` all future.

## Bad offers

| Flag | Why bad |
|------|---------|
| No `job.id` / no `job.context` | Unscoped — no deliverable defined. |
| `lock` not `hash` or missing | Payment not bound to your solution. |
| `rails` missing or no `paper` | No settlement rail. |
| Asset not FLOP or PAPER | Random token. |
| `expiresMs < now` | Already expired. |

## Clean examples

FLOP on blockrewards with hash lock and real job → clean.
FLOP on a2a with hash lock and real job → clean.
PAPER on pin (100 PAPER) with hash lock and real job → clean.
PAPER with rails `["paper", "flop-htlc"]` + hash lock + real job → highest
integrity (atomic swap via HTLC).

## Bad examples

1,000,000 PAPER with no job, hash lock, paper rail → bad (too much for
unscoped task). Random token XYZ_TOK with no rails → bad. FLOP with no lock
→ bad (payment not bound to solution).
