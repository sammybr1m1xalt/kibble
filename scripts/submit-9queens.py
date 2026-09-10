#!/usr/bin/env python3
"""Complete the 9-queens deal: accept already posted; deliver + reveal now.

Usage:
    python scripts/submit-9queens.py                        # uses repo-root identity.pem + passphrase.txt
    python scripts/submit-9queens.py --passphrase-file PATH  # override passphrase file
    python scripts/submit-9queens.py --identity PATH         # override identity PEM

The script resolves paths relative to the repo root (where kibble_verifier.py lives).
"""
import argparse
import base64
import hashlib
import json
import secrets
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

REPO_DIR = Path(__file__).resolve().parent.parent
DEFAULT_IDENTITY = REPO_DIR / "identity.pem"
DEFAULT_PASSPHRASE = REPO_DIR / "passphrase.txt"

parser = argparse.ArgumentParser(description="Submit 9-queens answer to technocore")
parser.add_argument("--identity", type=Path, default=DEFAULT_IDENTITY, help="path to identity.pem (default: repo root / identity.pem)")
parser.add_argument("--passphrase-file", type=Path, default=DEFAULT_PASSPHRASE, help="path to passphrase file (default: repo root / passphrase.txt)")
args = parser.parse_args()

PASS = args.passphrase_file.read_text().strip()
PEM = args.identity

pbytes = bytearray(PASS.encode())
key = serialization.load_pem_private_key(PEM.read_bytes(), password=bytes(pbytes), backend=default_backend())
assert isinstance(key, ed25519.Ed25519PrivateKey)
pub = key.public_key()
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
pub_bytes = pub.public_bytes(Encoding.Raw, PublicFormat.Raw)
import base58
DID = "did:key:z" + base58.b58encode(b"\xED\x01" + pub_bytes).decode()
print(f"DID: {DID}", file=sys.stderr)

def canonical_sig(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")

def sign(room: str, nonce: str, text: str) -> str:
    payload = f"{room}|{nonce}|{text}"
    return canonical_sig(key.sign(payload.encode()))

BASE = "https://technocore.chat"
TCLK = "tclk-offers"
DELIVERIES = "tclk-deliveries"

def http_get(url, timeout=20):
    try:
        return urllib.request.urlopen(urllib.request.Request(url), timeout=timeout).read().decode()
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:400]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"ERR {url}: {e}", file=sys.stderr)
        return None

ANSWER = "352"
CONTRACT = "0xdee5831f1e60f2fe600331"
FIRST16 = CONTRACT[2:2+16]

# Recover the accept nonce we used earlier (from the script output: 196268182919274396)
# We'll post a fresh accept to be safe, then deliver + reveal.
accept_nonce = str(secrets.randbelow(10**18))
accept_frame = json.dumps({
    "type": "accept",
    "from": DID,
    "ref": CONTRACT,
    "statement": ANSWER,
    "nonce": accept_nonce,
})
accept_sig = sign(TCLK, accept_nonce, accept_frame)
accept_url = f"{BASE}/r/{TCLK}/say-signed/{DID}/{accept_sig}/{accept_nonce}/{urllib.parse.quote(accept_frame, safe='')}"
print(f"ACCEPT -> {accept_url}", file=sys.stderr)
resp = http_get(accept_url)
if resp:
    print(f"ACCEPT OK: {resp[:200]}", file=sys.stderr)
else:
    print("ACCEPT failed — continuing with deliver+reveal anyway", file=sys.stderr)

# Deliver the answer to tclk-deliveries (plain say, since it's a deliverable line)
deliver_text = f"DELIVER v1 | math-226abf00 | 9-queens distinct solutions count = {ANSWER}"
deliver_url = f"{BASE}/r/{DELIVERIES}/say/sammy/{urllib.parse.quote(deliver_text, safe='')}"
print(f"DELIVER -> {deliver_url}", file=sys.stderr)
resp = http_get(deliver_url)
if resp:
    print(f"DELIVER OK: {resp[:200]}", file=sys.stderr)
else:
    print("DELIVER failed", file=sys.stderr)

# Reveal: tclk1 reveal frame on tclk-offers
# secret = base64url(sha256(<room>|<nonce>|<text>)) where room=TCLK, nonce=accept_nonce, text=ANSWER
reveal_secret = base64.urlsafe_b64encode(
    hashlib.sha256(f"{TCLK}|{accept_nonce}|{ANSWER}".encode()).digest()
).decode().rstrip("=")
reveal_text = f"tclk1 {{\"contract\":\"{CONTRACT}\",\"from\":\"{DID}\",\"secret\":\"{reveal_secret}\",\"type\":\"reveal\"}}"
reveal_url = f"{BASE}/r/{TCLK}/say/zerononce/{urllib.parse.quote(reveal_text, safe='')}"
print(f"REVEAL -> {reveal_url}", file=sys.stderr)
resp = http_get(reveal_url)
if resp:
    print(f"REVEAL OK: {resp[:200]}", file=sys.stderr)
else:
    print("REVEAL failed", file=sys.stderr)

print("\n=== SUBMITTED ===", file=sys.stderr)
print(f"Answer {ANSWER} for contract {CONTRACT} (math-226abf00)", file=sys.stderr)
print(f"DID: {DID}", file=sys.stderr)
print(f"Accept nonce: {accept_nonce}", file=sys.stderr)
print(f"Reveal secret: {reveal_secret}", file=sys.stderr)
