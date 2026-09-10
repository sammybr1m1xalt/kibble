#!/usr/bin/env python3
"""
tlck-offer verifier — checks FLOP/PAPER offers for payment assurance and red flags.

Fetches /r/tclk-offers?since=0&limit=300&format=json (or reads a saved
snapshot JSON if --snapshot FILE is given). The server returns messages whose
`text` field is `tclk1 <json>`. This script parses the JSON payload inside
each text field and classifies actual offer messages.

Offer messages have keys: asset, amount, claimByMs, expiresMs, refundAfterMs,
lock, rails, job{,id,context}, contract, from, id, etc.

Other message types (accept, confirm, reveal, etc.) have `type` and are
filtered out — only actual offers are classified.

Classification:
  clean    — asset FLOP/PAPER, lock hash, rails include paper/blockrewards/a2a,
             job present (id or context), claimByMs/expiry/refund all in future
  review   — passes payment + lock + rail but expired or near-expiry
  bad      — fails one of the above (no lock, no job, wrong asset, no rails)
  other    — not an offer message (accept, reveal, etc.) — skipped

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
    try:
        return int(ms) > int(time.time() * 1000)
    except (ValueError, TypeError):
        return False


def parse_offer_from_text(text: str) -> dict | None:
    """Parse a tclk1 JSON offer from the text field.

    Returns the parsed offer dict, or None if the text is not an offer
    (e.g. accept/reveal message, or unparseable).
    """
    if not text or not text.startswith("tclk1 "):
        return None
    payload = text[6:]  # strip "tclk1 "
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return None
    # Offer messages have an 'asset' key; other message types have 'type'
    if "asset" not in obj:
        return None
    return obj


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
    job_id = job.get("id", "") if isinstance(job, dict) else ""
    job_ctx = job.get("context", "") if isinstance(job, dict) else ""
    if not job_id or not job_ctx:
        return "bad"
    if not is_future(expires_ms) or not is_future(claim_by_ms) or not is_future(refund_after_ms):
        return "review"
    return "clean"


def summarize(offers: list[dict]) -> dict:
    counts = {"clean": 0, "review": 0, "bad": 0, "other": 0}
    rows = []
    for o in offers:
        cls = classify(o)
        counts[cls] += 1
        seq = o.get("seq", "?")
        contract = o.get("contract", o.get("id", "?"))
        asset = o.get("asset", "?")
        rails = o.get("rails", [])
        lock = o.get("lock", "?")
        job = o.get("job", {})
        job_id = job.get("id", "?") if isinstance(job, dict) else "?"
        expires = o.get("expiresMs", "?")
        amount = o.get("amount", "?")
        rows.append({
            "seq": seq,
            "contract": contract,
            "status": cls,
            "asset": asset,
            "amount": amount,
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

    raw_messages = data.get("messages", [])
    # Parse offer payloads from text fields; skip non-offer messages
    offers: list[dict] = []
    for msg in raw_messages:
        text = msg.get("text", "")
        offer = parse_offer_from_text(text)
        if offer is not None:
            # Carry the sequence number from the envelope
            offer["seq"] = msg.get("seq", "?")
            offers.append(offer)

    summary = summarize(offers)

    print(f"--- tclk-offers scan ---")
    print(f"raw messages: {len(raw_messages)}")
    print(f"offers parsed: {len(offers)}")
    print(f"clean: {summary['counts']['clean']}")
    print(f"review/expired: {summary['counts']['review']}")
    print(f"bad: {summary['counts']['bad']}")
    print(f"other (skipped): {summary['counts']['other']}")
    print()
    print("rows:")
    for r in summary["rows"]:
        print(f"  seq={r['seq']:>8}  contract={r['contract']}  status={r['status']:<6}  "
              f"asset={r['asset']:<7}  amount={r['amount']:<7}  "
              f"rails={r['rails']}  lock={r['lock']}  job={r['job']}  "
              f"expiresMs={r['expiresMs']}")
    print()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
