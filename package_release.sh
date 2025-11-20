#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
ARTIFACT_DIR="$BASE_DIR/dist"
PACKAGE_NAME="telegram_identity_monitor_$(date -u +%Y%m%d_%H%M%S)"
PACKAGE_DIR="$ARTIFACT_DIR/$PACKAGE_NAME"

rm -rf "$PACKAGE_DIR"
mkdir -p "$PACKAGE_DIR"
mkdir -p "$ARTIFACT_DIR"

FILES=(
    telegram_identity_audit.py
    telegram_bot_notifier.py
    config.yaml
    NOTICE
    readme.md
    launch_template.plist
    install_launch_agent.sh
    install_pi_service.sh
    cleanup_runs.py
    setup_dependencies.sh
)
DIRS=(docs targets)

for item in "${FILES[@]}"; do
    if [ -e "$BASE_DIR/$item" ]; then
        cp "$BASE_DIR/$item" "$PACKAGE_DIR/"
    fi
done

for dir in "${DIRS[@]}"; do
    if [ -d "$BASE_DIR/$dir" ]; then
        cp -R "$BASE_DIR/$dir" "$PACKAGE_DIR/"
    fi
done

tar -czf "$ARTIFACT_DIR/$PACKAGE_NAME.tar.gz" -C "$ARTIFACT_DIR" "$PACKAGE_NAME"
rm -rf "$PACKAGE_DIR"

echo "Packaged core files into $ARTIFACT_DIR/$PACKAGE_NAME.tar.gz"
