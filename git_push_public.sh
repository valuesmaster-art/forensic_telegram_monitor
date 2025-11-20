#!/usr/bin/env bash
# Helper to publish the sanitized codebase to a remote Git repository.
# Usage: ./git_push_public.sh <remote-url> [branch]

set -euo pipefail

REMOTE_URL=${1:-}
BRANCH=${2:-main}

if [[ -z "$REMOTE_URL" ]]; then
  echo "Usage: $0 <remote-url> [branch]" >&2
  echo "Example: $0 git@github.com:yourname/telegram-identity.git main" >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Initialize the repo if needed and point HEAD at the chosen branch.
if [[ ! -d .git ]]; then
  git init
  git symbolic-ref HEAD "refs/heads/${BRANCH}"
fi

# Ensure the origin remote points at the requested URL.
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi

# Refuse to push if sensitive files are tracked.
SENSITIVE_PATTERNS=(
  "config.yaml"
  "*.session"
  "targets"
  "logs"
  "dist"
)
for pattern in "${SENSITIVE_PATTERNS[@]}"; do
  if git ls-files --cached -- "$pattern" | grep -q .; then
    echo "Refusing to push: tracked sensitive path matches '$pattern'." >&2
    echo "Remove it from the index (git rm --cached <file>) and retry." >&2
    exit 1
  fi
done

git add -A
git status --short

read -r -p "Commit message [update evidence tooling]: " COMMIT_MSG
COMMIT_MSG=${COMMIT_MSG:-"update evidence tooling"}

if git diff --cached --quiet; then
  echo "No staged changes to commit."
else
  git commit -m "$COMMIT_MSG"
fi

git push -u origin "$BRANCH"
