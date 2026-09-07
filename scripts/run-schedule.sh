#!/usr/bin/env bash
# run-schedule.sh — cron wrapper for kibble_verifier.py --schedule
#
# Runs hourly. Each run fetches /r/kibble/export, computes stats,
# signs a snapshot with your DID, and writes it to out/snapshots/.
# Nothing is posted to /r/kibble.
#
# Passphrase is read from --passphrase-file (mode 600), loaded into
# a bytearray by kibble_verifier.py, zeroed after use. Never written
# to disk by the script.
#
# Install: crontab -e
#   0 * * * * /path/to/kibble-verifier/scripts/run-schedule.sh
#
# By default the script looks for passphrase.txt and identity.pem in the
# repo root. Override via KIBBLE_PASSPHRASE_FILE and KIBBLE_IDENTITY
# env vars, or edit the defaults below.
#
# The wrapper uses repo-relative paths resolved at runtime. If you run it
# from a cron job, set the working directory to the repo root or set REPO_DIR.

set -euo pipefail

# Repo root directory. Defaults to the directory containing this script's
# parent (i.e. the repo root when scripts/run-schedule.sh is run).
REPO_DIR="${REPO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"

# Passphrase file (mode 600). Default: repo root / passphrase.txt
PASSPHRASE_FILE="${KIBBLE_PASSPHRASE_FILE:-${REPO_DIR}/passphrase.txt}"

# Identity PEM (mode 600). Default: repo root / identity.pem
IDENTITY_FILE="${KIBBLE_IDENTITY:-${REPO_DIR}/identity.pem}"

LOG_FILE="${REPO_DIR}/out/cron.log"
PYTHON="${REPO_DIR}/.venv/bin/python"
VERIFIER="${REPO_DIR}/kibble_verifier.py"

log() {
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*" | tee -a "$LOG_FILE"
}

log "START schedule run"

if [ ! -f "$VERIFIER" ]; then
    log "ERROR: verifier not found: $VERIFIER"
    exit 1
fi

if [ ! -f "$PASSPHRASE_FILE" ]; then
    log "ERROR: passphrase file not found: $PASSPHRASE_FILE"
    exit 1
fi

if [ ! -f "$IDENTITY_FILE" ]; then
    log "ERROR: identity file not found: $IDENTITY_FILE"
    exit 1
fi

if [ ! -x "$PYTHON" ]; then
    log "ERROR: python not found: $PYTHON"
    exit 1
fi

# Run the verifier in schedule mode (dry-run + signed snapshot, no posting)
"$PYTHON" "$VERIFIER" --schedule \
    --passphrase-file "$PASSPHRASE_FILE" \
    --identity "$IDENTITY_FILE" \
    >> "$LOG_FILE" 2>&1

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    log "END schedule run: OK"
else
    log "END schedule run: FAILED (exit $EXIT_CODE)"
fi

exit $EXIT_CODE
