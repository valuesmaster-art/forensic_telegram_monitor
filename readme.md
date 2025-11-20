# Telegram Identity Monitoring Tool

A forensic-style Telethon script (`telegram_identity_audit.py`) that continuously acquires identity details and media from a target Telegram account while preserving evidential integrity via hashing and an anchor media file.

## Features
- Resolves target identity by UID, username, or phone
- Logs config and session SHA-256 hashes each run
- Establishes a permanent anchor media (first file retrieved) and verifies it on subsequent runs
- Records detailed identity summaries plus per-run media manifests with file hashes
- Hashes and logs timestamps for up to N textual message samples per run
- Captures the current profile photo (when available) with EXIF-embedded timestamps, hashed filenames, and `.sha256` sidecars
- Verifies configured message markers by hashing specific message texts + logging timestamps
- Includes the identity summary hash inside each per-run manifest, emits an audit report + `.sha256`, and maintains a master manifest referencing all runs
- Appends per-day `runs/<date>/status_timeline.csv` with every run so you can track last-seen status, last-active, and exact deletion detection time
- Creates `runs/<date>/day_summary.txt` + `day_identity_log.txt` to snapshot both the latest status and the full identity report for that date
- Hashes all retrieved media/attachments but does not retain per-run copies (only the anchor file persists), keeping run folders textual
- Gracefully detects network outages (`network_error` timeline entries) without treating them as deletions
- Optionally notifies you via a Telegram Bot when the monitored account is marked deleted
- Detects deletion indicators (RPC errors, `deleted` flag, missing anchor/media) and halts unless `--force-run`

## Requirements
```bash
pip install telethon pyyaml pillow
```
Create a Telegram API ID/hash at [my.telegram.org](https://my.telegram.org) and populate `config.yaml`.

## Configuration (`config.yaml`)
```yaml
api:
  id: 123456
  hash: "your_api_hash_here"
  session: "session_name"

target:
  uid: 123456789
  username: "example"
  phone: "+10000000000"
  address_book_name: "Contact Name"
  anchor_media_sha256: ""

acquisition:
  outdir: "targets"
  media_limit: 1000
  message_sample_count: 5

message_markers:
  - label: "Payment instruction"
    content: "Wire the funds to account XXXX"

bot:
  token: "123456:ABCDEF"
  chat_id: "987654321"
```
- `anchor_media_sha256` remains empty until the first run establishes the anchor.
- `outdir` defines the evidence root (`targets/<uid>/...`).
- `message_sample_count` controls how many textual messages are hashed + logged each run.
- `message_markers` lets you declare specific message texts that must be present; each entry includes a human label and the exact text content to match.
- `bot` (optional) holds the Telegram Bot token + chat ID used by `telegram_bot_notifier.py` to send deletion alerts.

## Usage
```bash
python3 telegram_identity_audit.py --config config.yaml
# optional: override the targets root for a single run
python3 telegram_identity_audit.py --config config.yaml --outdir /path/to/targets
```
1. First run authenticates via Telethon (creating `<session_name>.session`), downloads media, sets the anchor, and writes logs under `targets/<uid>/runs/<timestamp>/`.
2. Later runs hash the current config/session, verify the preserved anchor in `targets/<uid>/anchor_media/`, and append identity + manifest logs.
3. If deletion indicators occur, `targets/<uid>/account_deleted.txt` is written and monitoring stops unless `--force-run` is supplied.
4. Each run records up to `message_sample_count` textual messages (timestamp + content hash + preview) beneath the "Message Content Samples" section of `identity.txt`.
5. The current profile photo (if present) is saved into `targets/<uid>/profile_photos/` as `profile_<sha>.ext`, has its SHA-256 logged (truncated in the report, full in a `.sha256` sidecar), and receives an EXIF timestamp so the file’s creation date reflects the last captured change.
6. Configured message markers are tracked in `identity.txt` under "Configured Message Markers" with presence/absence, timestamps, hashes, and body text for evidential comparison.
7. Each run’s `manifest.txt` ends with the SHA-256 of `identity.txt`, an `audit_report.txt` plus `audit_report.txt.sha256` is generated, and `runs/<date>/master_manifest.txt` is appended with references (sha + relative path) to each run’s identity/manifest/audit files for that day.
8. `runs/<date>/status_timeline.csv` grows on every run that occurs on that date, listing the run timestamp, observed status, last active time, and whether deletion was detected (with the reason).
9. `runs/<date>/day_summary.txt` captures the latest status/last-active, while `day_identity_log.txt` appends the full `identity.txt` contents per run so evidence survives even if per-run folders are cleaned up later.
10. Per-run media are hashed and described in the manifest/identity sections but not retained on disk (only the anchor media remains for integrity checks).

Resetting evidence + anchor:
```bash
python3 telegram_identity_audit.py --config config.yaml --reset
```
This removes `targets/<uid>/` and clears `target.anchor_media_sha256` in the config, allowing a fresh anchor acquisition on the next run (useful when moving to a new machine or starting over).

Verifying deletion-stop behavior (no further logging once deleted):
```bash
python3 telegram_identity_audit.py --config config.yaml --verify-deletion-stop
```
This reports whether `account_deleted.txt` exists. When present, normal runs exit immediately (unless `--force-run`), ensuring no additional logging occurs after deletion detection.

Cleaning up active-day runs from the main script:
```bash
python3 telegram_identity_audit.py --config config.yaml --cleanup-all --cleanup-dry-run
python3 telegram_identity_audit.py --config config.yaml --cleanup-all
```
The flag behaves like `cleanup_runs.py`, iterating through `runs/<date>/` and deleting older per-run folders when the day ended with the account still active. The most recent run (and day-level summaries) are always retained. Use `--cleanup-dry-run` first to inspect the actions.

Cleaning up runs for active days:
```bash
python3 cleanup_runs.py --target-dir targets/<uid> --dry-run
python3 cleanup_runs.py --target-dir targets/<uid>
```
The helper removes older per-run folders (keeping `day_summary.txt`, `status_timeline.csv`, `master_manifest.txt`, `day_identity_log.txt`, and the newest run folder) when the day ended with the account still active. Use `--dry-run` first to see what would be deleted.

Telegram bot notifications (optional):
```bash
python3 telegram_bot_notifier.py --config config.yaml
# attach specific files (relative to latest run dir)
python3 telegram_bot_notifier.py --config config.yaml --attachments identity.txt manifest.txt audit_report.txt
# dry-run preview
python3 telegram_bot_notifier.py --config config.yaml --dry-run
# simulate using a specific run folder
python3 telegram_bot_notifier.py --config config.yaml --simulate-run targets/<uid>/runs/20250101/20250101_120000
```
Configure `bot.token` + `bot.chat_id` in `config.yaml`. Run the notifier manually or via cron/systemd to send a chat message when `account_deleted.txt` appears (notifications are sent once per deletion event). The notifier automatically attaches the latest profile photo plus any files specified via `--attachments`.

## Notes
- Ensure the monitored account is accessible (in contacts or resolvable via UID/username).
- You must already know the target’s UID, username, and phone number to run the tool; never attempt to monitor accounts without lawful authorization or consent.
- Maintain chain-of-custody procedures appropriate for your environment (e.g., version control, checksums of outputs).
- See `instruction.txt` for the complete system specification and behavioural requirements.
- Pillow is used to embed EXIF timestamps into stored profile photos; if it is unavailable, the script still runs but skips EXIF tagging.
- Each `runs/<date>/master_manifest.txt` provides a concise log of that day’s runs, listing hashes for identity/manifest/audit files so you can audit by date, and `day_identity_log.txt` stores the full `identity.txt` contents for every run.
- `--verify-deletion-stop` is a quick test harness to prove that once `account_deleted.txt` exists, subsequent executions halt before creating new run folders or logs.
- `runs/<date>/status_timeline.csv` is the authoritative chronology for that day’s activity/deletion evidence; correlate its rows with `day_summary.txt`, `day_identity_log.txt`, and audit reports to pinpoint the exact micro-interval when the account transitioned to deleted/unavailable.
- `runs/<date>/master_manifest.txt`, `day_summary.txt`, and `day_identity_log.txt` mirror the latest runs for that date, making it easy to see at directory level when the target was last active or flagged as deleted while still retaining the full narrative evidence per run.
- Network outages are recorded as `network_error` entries in the timeline/day summaries and never trigger deletion; rerun once connectivity is restored.
- Use `--cleanup-all` (or `cleanup_runs.py`) to prune per-run folders for days that remained active, keeping the final run plus the per-day summaries/logs.
- This tool logs metadata exactly as it appears to your own Telegram client. It cannot access messages, intercept communications, or view anything you aren’t already able to see. Only use this tool with accounts that are already visible to you in your Telegram contact list or chat history. All stored data is hashed or anonymised; no identifiable personal content is recorded.
- Loop helpers (manual automation):
```bash
./run_loop.sh 900                          # monitor every 900s
./run_loop.sh 900 logs/custom_monitor.log  # monitor with timestamped log
./run_notifier_loop.sh 1800                # notifier every 1800s
./run_notifier_loop.sh 1800 logs/custom_notifier.log
./run_all_loops.sh 900 1800                # launch both loops (logs placed in logs/)
```
Each loop logs the UTC timestamp for runs + sleeps, and writes to a timestamped log file if a path is provided.

Stopping the LaunchAgent:
```bash
launchctl stop com.example.telegram_identity_monitor
launchctl unload ~/Library/LaunchAgents/com.telegram.identity.monitor.plist
```
This halts background runs. Re-run `install_launch_agent.sh` (or load the plist) to start it again.
