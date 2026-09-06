#!/usr/bin/env bash
# run-schedule.sh — cron wrapper for kibble_verifier.py --schedule
#
# Install: crontab -e
#   0 * * * * /home/anon/technocore-did-starter/scripts/run-schedule.sh
#
# Runs hourly. Each run fetches /r/kibble/export, computes stats,
# signs a snapshot with your DID, and writes it to out/snapshots/.
# Nothing is posted to /r/kibble.
#
# Passphrase is read from --passphrase-file (mode 600), loaded into
# a bytearray by kibble_verifier.py, zeroed after use. Never written
# to disk by the script.

set -euo pipefail

REPO_DIR="/home/anon/technocore-did-starter"
PASSPHRASE_FILE="/home/anon/technocore-new/passphrase.txt"
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

if [ ! -x "$PYTHON" ]; then
    log "ERROR: python not found: $PYTHON"
    exit 1
fi

# Run the verifier in schedule mode (dry-run + signed snapshot, no posting)
"$PYTHON" "$VERIFIER" --schedule \
    --passphrase-file "$PASSPHRASE_FILE" \
    >> "$LOG_FILE" 2>&1

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    log "END schedule run: OK"
else
    log "END schedule run: FAILED (exit $EXIT_CODE)"
fi

exit $EXIT_CODE
