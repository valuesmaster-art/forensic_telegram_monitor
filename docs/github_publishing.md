# Publishing to GitHub (public-safe)

The repo now ships with `.gitignore` rules that block evidence and secrets (`config.yaml`, `targets/`, `*.session`, `logs/`, `dist/`). Use the steps below to publish a clean, reviewable copy for court/reference.

## Before you publish
- Leave `config.yaml`, session files, and `targets/` in place locally; they will stay untracked. If any are already tracked, remove them from the index: `git rm --cached <file>`.
- Use `config.example.yaml` as the shareable template; do not include real API IDs, hashes, or phone numbers.
- Inspect what will be published: `git status --short --ignored` (the ignored list should include evidence artifacts).

## First publish to GitHub
```bash
# pass your GitHub repo URL and desired branch (defaults to main)
./git_push_public.sh git@github.com:<user>/<repo>.git [branch]
```
The helper initializes Git if needed, sets `origin`, blocks pushes when sensitive files are tracked, stages changes, commits, and pushes.

## Pull updates later
```bash
./git_pull_public.sh [remote] [branch]   # defaults: origin main
```
This fetches and fast-forwards without touching ignored evidence data.

## Quick checklist for a court-facing repo
- No personal data: config/session/targets/logs/dist stay ignored.
- `NOTICE` and `readme.md` remain to describe lawful use and capabilities.
- Include `instruction.txt` to preserve the behavioural specification.
