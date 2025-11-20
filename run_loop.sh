#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$BASE_DIR/config.yaml"
INTERVAL="${1:-600}"
LOG_FILE="${2:-}"
PYTHON_BIN="$BASE_DIR/.venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

cd "$BASE_DIR"

if [ -n "$LOG_FILE" ]; then
  mkdir -p "$(dirname "$LOG_FILE")"
  ts="$(date -u '+%Y%m%d_%H%M%S')"
  LOG_FILE="${LOG_FILE%.log}_${ts}.log"
  exec >> "$LOG_FILE" 2>&1
  echo "[i] Logging to $LOG_FILE"
fi

while true; do
  echo "[i] $(date -u '+%Y-%m-%d %H:%M:%S') running audit"
  "$PYTHON_BIN" telegram_identity_audit.py --config "$CONFIG"
  echo "[i] $(date -u '+%Y-%m-%d %H:%M:%S') sleeping ${INTERVAL}s"
  sleep "$INTERVAL"
done
