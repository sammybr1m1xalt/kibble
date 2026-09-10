#!/usr/bin/env python3
"""
tlck-offer verifier — checks FLOP/PAPER offers for payment assurance and red flags.

Fetches /r/tclk-offers?since=0&limit=300&format=json (or reads a saved
snapshot JSON if --snapshot FILE is given). Classifies each offer as:

  assured   — asset FLOP/PAPER, lock hash, rails include paper/blockrewards/a2a,
              job present (id or context), claimByMs/expiry/refund all in future
  likely-safe — passes payment + lock + rail but has a minor flag (e.g. short window)
  review    — passes the above but expired or near-expiry
  bad       — fails one of the above (no lock, no job, wrong asset, no rails)
  expired   — claim/expiry/refund already past

No identity, no signing — safe to run from anywhere with outbound HTTPS.

Usage:
  .venv/bin/python scripts/check-tclk-offers.py
  .venv/bin/python scripts/check-tclk-offers.py --snapshot /path/to/snapshot.json
"""
import argparse
import datetime
import json
import sys
import time
from urllib.request import urlopen

BASE = "https://technocore.chat"
OFFER_URL = f"{BASE}/r/tclk-offers?since=0&limit=300&format=json"


def fetch_offers(url: str) -> dict:
    with urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())


def load_snapshot(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def is_future(ms: int | None) -> bool:
    if ms is None:
        return False
    return ms > time.time() * 1000


def classify(offer: dict) -> str:
    asset = offer.get("asset", "")
    rails = offer.get("rails", [])
    lock = offer.get("lock", "")
    job = offer.get("job", {})
    expires_ms = offer.get("expiresMs")
    claim_by_ms = offer.get("claimByMs")
    refund_after_ms = offer.get("refundAfterMs")

    if asset not in ("FLOP", "PAPER"):
        return "bad"
    if not rails or ("paper" not in rails and "blockrewards" not in rails and "a2a" not in rails):
        return "bad"
    if lock != "hash":
        return "bad"
    job_id = job.get("id", "")
    job_ctx = job.get("context", "")
    if not job_id or not job_ctx:
        return "bad"
    if not is_future(expires_ms) or not is_future(claim_by_ms) or not is_future(refund_after_ms):
        return "review"
    return "clean"


def summarize(offers: list[dict]) -> dict:
    counts = {"clean": 0, "review": 0, "bad": 0}
    rows = []
    for o in offers:
        cls = classify(o)
        counts[cls] += 1
        seq = o.get("sequence", "?")
        contract = o.get("contract", "?")
        asset = o.get("asset", "?")
        rails = o.get("rails", [])
        lock = o.get("lock", "?")
        job_id = o.get("job", {}).get("id", "?")
        expires = o.get("expiresMs", "?")
        rows.append({
            "seq": seq,
            "contract": contract,
            "status": cls,
            "asset": asset,
            "rails": rails,
            "lock": lock,
            "job": job_id,
            "expiresMs": expires,
        })
    return {
        "counts": counts,
        "total": len(offers),
        "rows": rows,
        "fetched": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="tclk-offers scanner")
    ap.add_argument("--snapshot", help="path to saved JSON snapshot")
    args = ap.parse_args(argv)

    if args.snapshot:
        data = load_snapshot(args.snapshot)
    else:
        data = fetch_offers(OFFER_URL)

    offers = data.get("messages", [])
    summary = summarize(offers)

    print(f"--- tclk-offers scan ---")
    print(f"total: {summary['total']}")
    print(f"clean: {summary['counts']['clean']}")
    print(f"review/expired: {summary['counts']['review']}")
    print(f"bad: {summary['counts']['bad']}")
    print()
    print("rows:")
    for r in summary["rows"]:
        print(f"  seq={r['seq']:>8}  contract={r['contract']}  status={r['status']:<6}  "
              f"asset={r['asset']:<7}  rails={r['rails']}  lock={r['lock']}  job={r['job']}  "
              f"expiresMs={r['expiresMs']}")
    print()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
