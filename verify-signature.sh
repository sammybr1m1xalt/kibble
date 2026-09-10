#!/usr/bin/env bash
# verify-signature.sh — verify an Ed25519 signature from identity.pem
#
# Usage:
#   ./verify-signature.sh <message> <base64_signature>
#   ./verify-signature.sh "hello world" "$(cat sig.b64)"
#
# The message is $1, the base64 signature is $2.
# PEM: identity.pem (Ed25519 private key, encrypted)
# Passphrase: from passphrase.txt (raw string, one line)
#
# Exit codes:
#   0 — signature VALID
#   1 — signature INVALID or usage error
#   2 — crypto/library error

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PEM_FILE="${SCRIPT_DIR}/identity.pem"
PASSPHRASE_FILE="${SCRIPT_DIR}/passphrase.txt"

# --- Args ---
if [ $# -lt 2 ]; then
    echo "Usage: $0 <message> <base64_signature>" >&2
    echo "       $0 'hello world' 'base64sig...'" >&2
    exit 1
fi

MESSAGE="$1"
BASE64_SIG="$2"

if [ ! -f "$PEM_FILE" ]; then
    echo "ERROR: identity.pem not found at $PEM_FILE" >&2
    exit 2
fi

if [ ! -f "$PASSPHRASE_FILE" ]; then
    echo "ERROR: passphrase.txt not found at $PASSPHRASE_FILE" >&2
    exit 2
fi

# --- Verify via embedded python3 ---
# Reads PEM + passphrase, decodes base64 sig, verifies Ed25519 sig against message.
python3 - "$MESSAGE" "$BASE64_SIG" "$PEM_FILE" "$PASSPHRASE_FILE" << 'PYEOF'
import sys
import base64

# Args passed by bash
message = sys.argv[1]
base64_sig = sys.argv[2]
pem_path = sys.argv[3]
passphrase_path = sys.argv[4]

# Read passphrase
with open(passphrase_path, "r") as f:
    passphrase = f.read().strip()

# Read PEM
with open(pem_path, "rb") as f:
    pem_bytes = f.read()

# Load key
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import ed25519

try:
    private_key = serialization.load_pem_private_key(
        pem_bytes, password=passphrase.encode("utf-8"), backend=default_backend()
    )
except Exception as e:
    print(f"ERROR: failed to load identity.pem: {e}", file=sys.stderr)
    sys.exit(2)

# Decode signature
try:
    sig_bytes = base64.b64decode(base64_sig)
except Exception as e:
    print(f"ERROR: invalid base64 signature: {e}", file=sys.stderr)
    sys.exit(2)

# Verify
message_bytes = message.encode("utf-8")
try:
    if not isinstance(private_key, ed25519.Ed25519PrivateKey):
        print("ERROR: key is not Ed25519", file=sys.stderr)
        sys.exit(2)
    public_key = private_key.public_key()
    public_key.verify(sig_bytes, message_bytes)
    print("VALID")
    sys.exit(0)
except Exception as e:
    # cryptography raises InvalidSignature on failure
    print(f"INVALID ({e})")
    sys.exit(1)
PYEOF
