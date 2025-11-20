#!/usr/bin/env python3
"""Notify via Telegram Bot when a monitored account is marked deleted."""
import argparse
import pathlib
import urllib.parse
import urllib.request
import mimetypes
import uuid
import yaml

API_BASE = "https://api.telegram.org"

def _post_multipart(url: str, fields: dict, files: dict):
    boundary = uuid.uuid4().hex
    data = []
    for name, value in fields.items():
        data.append(f"--{boundary}\r\n")
        data.append(f"Content-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n")
    for name, file_path in files.items():
        filename = file_path.name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        data.append(f"--{boundary}\r\n")
        data.append(
            f"Content-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n"
        )
        data.append(file_path.read_bytes())
        data.append("\r\n")
    data.append(f"--{boundary}--\r\n")
    body = b"".join(x if isinstance(x, bytes) else x.encode("utf-8") for x in data)

    req = urllib.request.Request(url, data=body)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(req, timeout=60) as resp:  # nosec B310
        resp.read()

def send_message(token: str, chat_id: str, text: str, attachments=None):
    attachments = attachments or []
    endpoint = f"{API_BASE}/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(endpoint, data=data)
    with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
        resp.read()

    if attachments:
        send_document = f"{API_BASE}/bot{token}/sendDocument"
        for file_path in attachments:
            _post_multipart(
                send_document,
                {"chat_id": chat_id, "caption": file_path.name},
                {"document": file_path},
            )

def main():
    parser = argparse.ArgumentParser(description="Notify when account_deleted.txt appears")
    parser.add_argument("--config", required=True)
    parser.add_argument("--target-dir", help="Optional explicit targets/<uid> directory")
    parser.add_argument("--attachments", nargs="*", default=["identity.txt", "audit_report.txt"],
                        help="Files (relative to last run dir) to send when deleted")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be sent without contacting the Telegram API")
    parser.add_argument("--simulate-run",
                        help="Path to runs/<date>/<timestamp>/ directory for sending a test notification")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).resolve()
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    bot_cfg = cfg.get("bot") or {}
    token = bot_cfg.get("token")
    chat_id = bot_cfg.get("chat_id")
    if not token or not chat_id:
        raise SystemExit("bot.token and bot.chat_id must be set in config.yaml")

    target_dir = pathlib.Path(args.target_dir).resolve() if args.target_dir else pathlib.Path(cfg["acquisition"]["outdir"]).resolve() / str(cfg["target"]["uid"])

    simulate_run_dir = pathlib.Path(args.simulate_run).resolve() if args.simulate_run else None
    if simulate_run_dir:
        if not simulate_run_dir.is_dir():
            raise SystemExit(f"simulate run directory not found: {simulate_run_dir}")
        runs_dir = simulate_run_dir.parent.parent  # .../runs/<date>/<run>
        target_dir = runs_dir.parent
        message = (
            f"SIMULATION — Telegram monitor test for UID {cfg['target']['uid']}\n"
            f"Using run folder: {simulate_run_dir}"
        )
        deletion_text = "simulation"
    else:
        deletion_file = target_dir / "account_deleted.txt"
        if not deletion_file.exists():
            print("[i] No deletion flag present; nothing to notify.")
            return

        notify_dir = target_dir / "notifications"
        notify_dir.mkdir(exist_ok=True)
        state_file = notify_dir / "deletion_notified.txt"

        deletion_text = deletion_file.read_text(encoding="utf-8")
        if state_file.exists() and state_file.read_text(encoding="utf-8") == deletion_text:
            print("[i] Deletion already notified.")
            return

        message = (
            f"Account deletion detected for UID {cfg['target']['uid']}\n"
            f"Details:\n{deletion_text}"
        )

    attachments = []
    if simulate_run_dir:
        run_dirs = [simulate_run_dir]
    else:
        runs_dir = target_dir / "runs"
        day_dirs = sorted(p for p in runs_dir.iterdir() if p.is_dir())
        run_dirs = []
        if day_dirs:
            last_day = day_dirs[-1]
            run_dirs = sorted(p for p in last_day.iterdir() if p.is_dir())

    if run_dirs:
        last_run = run_dirs[-1]
        for rel_path in args.attachments:
            path = (last_run / rel_path).resolve()
            if path.exists():
                attachments.append(path)

    profile_dir = target_dir / "profile_photos"
    profile_files = sorted(profile_dir.glob("profile_*")) if profile_dir.exists() else []
    if profile_files:
        attachments.append(profile_files[-1])

    print("[i] Notification preview:\n" + message)
    if attachments:
        print("[i] Attachments:")
        for path in attachments:
            print(f"  - {path}")

    if args.dry_run:
        print("[DRY-RUN] No message sent.")
        return

    send_message(token, chat_id, message, attachments)
    if not simulate_run_dir:
        state_file.write_text(deletion_text, encoding="utf-8")
    print("[✓] Notification sent (with attachments)." if attachments else "[✓] Notification sent.")

if __name__ == "__main__":
    main()
