#!/usr/bin/env bash
# Helper to pull updates from the public repository without touching evidence.
# Usage: ./git_pull_public.sh [remote] [branch]

set -euo pipefail

REMOTE=${1:-origin}
BRANCH=${2:-main}

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -d .git ]]; then
  echo "No .git directory found. Run git init and add the remote first." >&2
  exit 1
fi

git fetch "$REMOTE" "$BRANCH"
git pull --ff-only "$REMOTE" "$BRANCH"
