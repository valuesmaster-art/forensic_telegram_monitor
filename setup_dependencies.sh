#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$BASE_DIR/.venv"
PY_BIN="${PY_BIN:-python3}"
REQS=(telethon pyyaml pillow)

if [ ! -d "$VENV" ]; then
  echo "[*] Creating virtualenv at $VENV"
  "$PY_BIN" -m venv "$VENV"
fi

PIP_BIN="$VENV/bin/pip"

echo "[*] Upgrading pip in $VENV"
"$VENV/bin/python" -m pip install --upgrade pip

echo "[*] Installing dependencies into $VENV"
"$PIP_BIN" install "${REQS[@]}"

echo "[✓] Dependencies installed into $VENV"
