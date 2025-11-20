#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
MONITOR_INTERVAL=${1:-900}
NOTIFY_INTERVAL=${2:-1800}

cd "$BASE_DIR"
ts="$(date -u '+%Y%m%d_%H%M%S')"

mkdir -p logs
monitor_log="logs/monitor_loop_${ts}.log"
notifier_log="logs/notifier_loop_${ts}.log"

echo "[i] Launching monitor loop every $MONITOR_INTERVAL s → $monitor_log"
nohup ./run_loop.sh "$MONITOR_INTERVAL" "$monitor_log" >/dev/null 2>&1 &
monitor_pid=$!

echo "[i] Launching notifier loop every $NOTIFY_INTERVAL s → $notifier_log"
nohup ./run_notifier_loop.sh "$NOTIFY_INTERVAL" "$notifier_log" >/dev/null 2>&1 &
notifier_pid=$!

echo "Monitor PID: $monitor_pid"
echo "Notifier PID: $notifier_pid"
