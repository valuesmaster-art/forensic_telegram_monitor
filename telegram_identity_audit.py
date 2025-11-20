#!/usr/bin/env python3
"""
telegram_identity_audit.py — Telegram Identity Monitoring + Anchor Acquisition
-------------------------------------------------------------------------------

• Reads YAML config describing API credentials + target identity.
• On first run:
      - Establishes anchor media
      - Stores anchor SHA-256 in config
      - Stores session file SHA-256
• On later runs:
      - Verifies anchor media SHA-256
      - Detects account deletion or alteration
• Logs all activity into timestamped run folders
• Stops monitoring permanently if deletion is detected (unless --force-run)

Usage:
    python3 telegram_identity_audit.py --config config.yaml
"""

import os
import sys
import time
import yaml
import hashlib
import argparse
import pathlib
import asyncio
import shutil
from datetime import datetime, timezone
from io import BytesIO

try:
    from PIL import Image
except ImportError:
    Image = None
from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import (
    User,
    PeerUser,
    UserStatusEmpty,
    UserStatusOnline,
    UserStatusOffline,
    UserStatusRecently,
    UserStatusLastWeek,
    UserStatusLastMonth,
)


# -------------------------------------------------------------------
# Utility hashing
# -------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# -------------------------------------------------------------------
# Formatting helpers
# -------------------------------------------------------------------

def fmt_utc(dt) -> str:
    """Return a human-readable UTC timestamp for datetime/epoch inputs."""
    if not dt:
        return "unknown"
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    if isinstance(dt, (int, float)):
        return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(dt))
    return str(dt)


def describe_status(status) -> str:
    """Convert Telethon user status objects into descriptive text."""
    if not status:
        return "unknown"

    if isinstance(status, UserStatusEmpty):
        return "hidden"
    if isinstance(status, UserStatusOnline):
        expiry = fmt_utc(getattr(status, "expires", None))
        return f"online (session expires {expiry})" if expiry != "unknown" else "online"
    if isinstance(status, UserStatusOffline):
        last = fmt_utc(getattr(status, "was_online", None))
        return f"offline (last seen {last})" if last != "unknown" else "offline"
    if isinstance(status, UserStatusRecently):
        return "recently active (last seen within ~2 days)"
    if isinstance(status, UserStatusLastWeek):
        return "last seen within 7 days"
    if isinstance(status, UserStatusLastMonth):
        return "last seen within 30 days"

    return type(status).__name__


def last_active_from_status(status) -> str:
    """Extract a single UTC timestamp for 'last active' when possible."""
    if isinstance(status, UserStatusOnline):
        return fmt_utc(getattr(status, "expires", None))
    if isinstance(status, UserStatusOffline):
        return fmt_utc(getattr(status, "was_online", None))
    return "unknown"


def embed_profile_timestamp(image_path: pathlib.Path, stamp: str):
    """Embed run timestamp into EXIF DateTime tags when Pillow is available."""
    if Image is None:
        return
    try:
        exif_stamp = datetime.strptime(stamp, "%Y%m%d_%H%M%S").strftime("%Y:%m:%d %H:%M:%S")
    except ValueError:
        return

    try:
        with Image.open(image_path) as img:
            exif = img.getexif()
            for tag in (306, 36867, 36868):  # DateTime, DateTimeOriginal, DateTimeDigitized
                exif[tag] = exif_stamp
            img.save(image_path, exif=exif)
    except Exception:
        pass


# -------------------------------------------------------------------
# Cleanup helpers
# -------------------------------------------------------------------

# -------------------------------------------------------------------
# Status helpers
# -------------------------------------------------------------------

def log_info(message: str):
    print(f"[i] {message}")

def log_warning(message: str):
    print(f"[!] {message}")

def log_alert(message: str):
    banner = "=" * 60
    print(f"\n{banner}\n[ALERT] {message}\n{banner}\n")


# -------------------------------------------------------------------
# Cleanup helpers
# -------------------------------------------------------------------

DAY_ALLOWED_FILES = {
    "day_summary.txt",
    "status_timeline.csv",
    "master_manifest.txt",
    "day_identity_log.txt",
}


def parse_day_summary_file(path: pathlib.Path):
    """
    Return dict with deleted/status fields or None if missing.
    """
    if not path.exists():
        return None
    deleted = None
    status = ""
    note = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        lower = line.lower()
        if lower.startswith("status:"):
            status = line.split(":", 1)[1].strip()
        elif lower.startswith("deleted flag:"):
            try:
                deleted = bool(int(line.split(":", 1)[1].strip()))
            except ValueError:
                deleted = None
        elif lower.startswith("note:"):
            note = line.split(":", 1)[1].strip()
    return {"deleted": deleted, "status": status, "note": note}


def cleanup_day_folder(date_dir: pathlib.Path, dry_run: bool = False):
    """
    Remove per-run artifacts within a date directory when the day's summary
    indicates the account remained active (no deletion/network errors).
    Keeps only the final run folder for that date.
    Returns (success_flag, message).
    """
    summary = parse_day_summary_file(date_dir / "day_summary.txt")
    if not summary:
        return False, "missing day_summary.txt"
    if summary["deleted"]:
        return False, "deletion detected"
    if summary["status"].lower() in {"network_error", "unresolved"}:
        return False, f"status {summary['status']}"

    run_dirs = sorted(p for p in date_dir.iterdir() if p.is_dir())
    if not run_dirs:
        return True, "no run folders to clean"

    keep_dir = run_dirs[-1]
    to_remove = run_dirs[:-1]

    removed_items = [p.name for p in to_remove]
    if not dry_run:
        for item in to_remove:
            shutil.rmtree(item)

        prune_day_identity_log(date_dir / "day_identity_log.txt", keep_dir.name)
        prune_day_master_manifest(date_dir / "master_manifest.txt", keep_dir.name)

    if not removed_items:
        return True, f"nothing to remove; keeping {keep_dir.name}"

    if dry_run:
        return True, f"would remove: {', '.join(removed_items)}; keep {keep_dir.name}"
    return True, f"removed: {', '.join(removed_items)}; kept {keep_dir.name}"


def prune_day_identity_log(log_path: pathlib.Path, keep_stamp: str):
    if not log_path.exists():
        return
    blocks = []
    current_stamp = None
    current_lines = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("=== Run ") and line.rstrip().endswith(" ==="):
                if current_stamp is not None:
                    blocks.append((current_stamp, "".join(current_lines)))
                current_stamp = line.strip()[len("=== Run "):-len(" ===")]
                current_lines = [line]
            else:
                current_lines.append(line)
    if current_stamp is not None:
        blocks.append((current_stamp, "".join(current_lines)))

    keep_block = next((block for stamp, block in blocks if stamp == keep_stamp), None)
    if keep_block is None:
        return
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(keep_block.strip("\n") + "\n")


def prune_day_master_manifest(path: pathlib.Path, keep_stamp: str):
    if not path.exists():
        return
    blocks = []
    current_stamp = None
    current_lines = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("Run: "):
                if current_stamp is not None:
                    blocks.append((current_stamp, "".join(current_lines)))
                current_stamp = line.strip().split("Run: ", 1)[1]
                current_lines = [line]
            else:
                current_lines.append(line)
    if current_stamp is not None:
        blocks.append((current_stamp, "".join(current_lines)))

    keep_block = next((block for stamp, block in blocks if stamp == keep_stamp), None)
    if keep_block is None:
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(keep_block.strip("\n") + "\n")


# -------------------------------------------------------------------
# YAML config load/save
# -------------------------------------------------------------------

def load_config(path: pathlib.Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def save_config(path: pathlib.Path, cfg: dict):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, sort_keys=False)


# -------------------------------------------------------------------
# Telethon helpers
# -------------------------------------------------------------------

async def safe_get_full_user(client: TelegramClient, entity):
    """
    Return full user info or raise signals for deletion/missing user.
    """
    try:
        full = await client(GetFullUserRequest(entity))
        return getattr(full, "user", None) or full
    except (ConnectionError, asyncio.TimeoutError, OSError) as e:
        return {"network_error": str(e)}
    except RPCError as e:
        return {"rpc_error": str(e)}


# -------------------------------------------------------------------
# Main monitoring logic
# -------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--force-run", action="store_true",
                        help="Run even if deletion already logged")
    parser.add_argument("--reset", action="store_true",
                        help="Delete target artifacts and clear anchor hash, then exit")
    parser.add_argument("--verify-deletion-stop", action="store_true",
                        help="Check whether deletion flag is present (no monitoring), then exit")
    parser.add_argument("--cleanup-all", action="store_true",
                        help="Remove per-run artifacts for days that ended without deletion")
    parser.add_argument("--cleanup-dry-run", action="store_true",
                        help="When used with --cleanup-all, show what would be removed without deleting")
    parser.add_argument("--outdir", default=None,
                        help="Override acquisition.outdir (targets folder root) for this run")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).resolve()
    cfg = load_config(cfg_path)

    # SHA-256 hash of config for identity logs
    config_text = yaml.dump(cfg, sort_keys=False)
    config_sha = sha256_text(config_text)

    # Extract config values
    api_id = cfg["api"]["id"]
    api_hash = cfg["api"]["hash"]
    session_name = cfg["api"]["session"]
    acquisition_cfg = cfg.get("acquisition", {})
    configured_outdir = acquisition_cfg["outdir"]
    outdir_override = args.outdir
    out_base = pathlib.Path(outdir_override or configured_outdir).resolve()
    message_sample_limit = int(acquisition_cfg.get("message_sample_count", 0) or 0)
    media_limit = int(acquisition_cfg.get("media_limit", 1000) or 1000)
    markers_cfg = cfg.get("message_markers") or []

    uid = cfg["target"]["uid"]
    username = cfg["target"].get("username")
    phone = cfg["target"].get("phone")
    address_name = cfg["target"].get("address_book_name", "")
    marker_targets = []
    marker_hits = {}
    for idx, entry in enumerate(markers_cfg):
        if not isinstance(entry, dict):
            continue
        content = entry.get("content")
        if not content:
            continue
        label = entry.get("label") or f"marker_{idx + 1}"
        marker_targets.append({
            "label": label,
            "content": content,
            "expected_sha": sha256_text(content),
        })
        marker_hits[label] = None

    # Prepare/reset target folder
    target_dir = out_base / str(uid)

    if args.reset:
        if target_dir.exists():
            shutil.rmtree(target_dir)
        cfg["target"]["anchor_media_sha256"] = ""
        save_config(cfg_path, cfg)
        log_info(f"Reset complete for target {uid}. Anchor hash cleared.")
        return

    target_dir.mkdir(parents=True, exist_ok=True)

    runs_dir = target_dir / "runs"
    runs_dir.mkdir(exist_ok=True)

    anchor_dir = target_dir / "anchor_media"
    anchor_dir.mkdir(exist_ok=True)

    profile_dir = target_dir / "profile_photos"
    profile_dir.mkdir(exist_ok=True)

    deletion_flag = target_dir / "account_deleted.txt"

    if args.cleanup_all:
        any_removed = False
        for date_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
            success, msg = cleanup_day_folder(date_dir, args.cleanup_dry_run)
            if success:
                any_removed = True
                prefix = "[DRY-RUN]" if args.cleanup_dry_run else "[✓]"
                log_info(f"{prefix} {date_dir.name}: {msg}")
            else:
                log_warning(f"[skip] {date_dir.name}: {msg}")
        if not any_removed:
            log_info("No eligible date folders for cleanup.")
        return

    if args.verify_deletion_stop:
        if deletion_flag.exists():
            log_info("account_deleted.txt present — monitoring halted until --force-run.")
        else:
            log_info("account_deleted.txt not present — monitoring will proceed on next run.")
        return

    if deletion_flag.exists() and not args.force_run:
        log_warning("Account deletion previously detected. Monitoring halted.")
        sys.exit(0)

    # Prepare timestamped run directory
    stamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    date_part = stamp.split("_", 1)[0]
    date_dir = runs_dir / date_part
    date_dir.mkdir(exist_ok=True)
    run_dir = date_dir / stamp
    run_dir.mkdir()
    log_info(f"Starting run {stamp} (UTC) for UID {uid} → {run_dir}")

    identity_path = run_dir / "identity.txt"
    manifest_path = run_dir / "manifest.txt"
    day_summary_path = date_dir / "day_summary.txt"
    timeline_path = date_dir / "status_timeline.csv"
    date_master_manifest_path = date_dir / "master_manifest.txt"
    day_identity_log_path = date_dir / "day_identity_log.txt"

    deletion_triggered = False

    def append_timeline_entry(status: str, last_active_value: str, deleted: bool, reason: str = ""):
        safe_status = (status or "unknown").replace("\n", " ")
        safe_last = (last_active_value or "unknown").replace("\n", " ")
        safe_reason = (reason or "").replace("\n", " | ")
        header = "run_timestamp,account_status,last_active_utc,deleted_flag,deletion_reason\n"
        needs_header = not timeline_path.exists()
        with open(timeline_path, "a", encoding="utf-8") as tf:
            if needs_header:
                tf.write(header)
            tf.write(f"{stamp},{safe_status},{safe_last},{1 if deleted else 0},{safe_reason}\n")

        update_day_summary(safe_status, safe_last, deleted, safe_reason)

    def update_day_summary(status: str, last_active_value: str, deleted: bool, reason: str):
        with open(day_summary_path, "w", encoding="utf-8") as df:
            df.write(f"Date: {date_part}\n")
            df.write(f"Last Run Timestamp: {stamp}\n")
            df.write(f"Status: {status or 'unknown'}\n")
            df.write(f"Last Active (UTC): {last_active_value or 'unknown'}\n")
            df.write(f"Deleted Flag: {int(bool(deleted))}\n")
            if reason:
                df.write(f"Note: {reason}\n")

    def append_day_identity_log():
        with open(identity_path, "r", encoding="utf-8") as src, \
             open(day_identity_log_path, "a", encoding="utf-8") as dest:
            dest.write(f"\n=== Run {stamp} ===\n")
            dest.write(src.read())
            dest.write("\n")

    def record_deletion(reason: str, status_context: str = "deleted", last_active_context: str = "unknown"):
        nonlocal deletion_triggered
        if deletion_triggered:
            return
        deletion_triggered = True
        with open(deletion_flag, "w", encoding="utf-8") as df:
            df.write(f"Deletion detected at UTC {stamp}\n")
            df.write(reason.strip() + "\n")
        log_alert(f"ACCOUNT DELETION DETECTED — {reason.strip()}")
        append_timeline_entry(status_context or "deleted",
                              last_active_context or "unknown",
                              True,
                              reason)

    # Compute SHA-256 of session file if exists
    session_file = pathlib.Path(f"{session_name}.session")
    session_sha = sha256_file(session_file) if session_file.exists() else "not_found"

    # Initialize Telethon
    client = TelegramClient(session_name, api_id, api_hash)
    await client.start()

    # Basic identity resolution
    user_entity = None

    # Priority 1: UID
    try:
        user_entity = await client.get_entity(PeerUser(uid))
    except:
        pass

    # Priority 2: Username
    if not user_entity and username:
        try:
            user_entity = await client.get_entity(username)
        except:
            pass

    # Priority 3: Phone/contacts
    if not user_entity and phone:
        try:
            for c in await client.get_contacts():
                if getattr(c, "phone", None) == phone:
                    user_entity = c
                    break
        except:
            pass

    # Write start of identity summary
    with open(identity_path, "w", encoding="utf-8") as idf:
        idf.write("TELEGRAM IDENTITY AUDIT\n")
        idf.write("=======================\n\n")
        idf.write(f"Run Timestamp (UTC): {stamp}\n")
        idf.write(f"Config SHA256: {config_sha}\n")
        idf.write(f"Session SHA256: {session_sha}\n\n")
        idf.write("Target Identifiers\n------------------\n")
        idf.write(f"UID: {uid}\n")
        idf.write(f"Username: {username}\n")
        idf.write(f"Phone: {phone}\n")
        idf.write(f"Address Book Name: {address_name}\n\n")

    if not user_entity:
        with open(identity_path, "a", encoding="utf-8") as idf:
            idf.write("[!] Could not resolve target entity via UID/username/phone\n")
        log_warning("Could not resolve target entity via UID/username/phone.")
        append_timeline_entry("unresolved", "unknown", False,
                              "entity resolution failed (uid/username/phone)")
        await client.disconnect()
        return

    # Pull full user info
    full = await safe_get_full_user(client, user_entity)

    # Detect deletion via RPC error
    if isinstance(full, dict) and "network_error" in full:
        network_msg = full["network_error"]
        with open(identity_path, "a", encoding="utf-8") as idf:
            idf.write("NETWORK STATUS: Connectivity unavailable\n")
            idf.write(f"Details: {network_msg}\n")

        log_warning(f"Network issue while querying account: {network_msg}")
        append_timeline_entry("network_error", "unknown", False, network_msg)
        await client.disconnect()
        return

    if isinstance(full, dict) and "rpc_error" in full:
        with open(identity_path, "a", encoding="utf-8") as idf:
            idf.write("ACCOUNT STATUS: Deleted/Unavailable\n")
            idf.write(f"RPC error: {full['rpc_error']}\n")

        record_deletion(f"RPC error: {full['rpc_error']}", "rpc_error", "unknown")

        await client.disconnect()
        return

    # Extract identity info with fallback to resolved entity (some accounts hide data)
    def _field(attr: str) -> str:
        primary = getattr(full, attr, None)
        if primary:
            return primary
        return getattr(user_entity, attr, "") or ""

    first = _field("first_name")
    last = _field("last_name")
    uname = _field("username")
    phone_current = _field("phone")
    status_obj = getattr(full, "status", None) or getattr(user_entity, "status", None)
    status_desc = describe_status(status_obj)
    status_raw = type(status_obj).__name__ if status_obj else "None"
    last_active = last_active_from_status(status_obj)
    deleted_flag = getattr(full, "deleted", False)

    # Download current profile photo (if any)
    profile_photo_sha = "not_available"
    profile_photo_last_updated = "unknown"
    try:
        temp_profile_path = profile_dir / f"profile_tmp_{stamp}"
        downloaded = await client.download_profile_photo(user_entity, file=temp_profile_path)
        if downloaded:
            photo_path = pathlib.Path(downloaded)
            profile_photo_sha = sha256_file(photo_path)
            suffix = photo_path.suffix or ".bin"

            existing_file = None
            for candidate in profile_dir.glob(f"profile_{profile_photo_sha}.*"):
                if candidate.suffix != ".sha256":
                    existing_file = candidate
                    break

            if existing_file:
                final_path = pathlib.Path(existing_file)
            else:
                final_path = profile_dir / f"profile_{profile_photo_sha}{suffix}"
                final_path.write_bytes(photo_path.read_bytes())
                embed_profile_timestamp(final_path, stamp)

            sha_path = final_path.with_suffix(final_path.suffix + ".sha256")
            try:
                sha_path.write_text(profile_photo_sha, encoding="utf-8")
            except OSError:
                pass

            stat = final_path.stat()
            birth = getattr(stat, "st_birthtime", None)
            profile_photo_last_updated = fmt_utc(birth or stat.st_mtime)

            if photo_path.exists():
                try:
                    photo_path.unlink()
                except OSError:
                    pass
        else:
            profile_photo_sha = "no_photo"
            if temp_profile_path.exists():
                try:
                    temp_profile_path.unlink()
                except OSError:
                    pass
    except Exception as e:
        profile_photo_sha = f"error: {e}"

    # Log identity
    with open(identity_path, "a", encoding="utf-8") as idf:
        idf.write("Identity Details\n-----------------\n")
        idf.write(f"Name: {first} {last}\n")
        idf.write(f"Username: {uname}\n")
        idf.write(f"Phone: {phone_current}\n")
        idf.write(f"Status: {status_desc}\n")
        idf.write(f"Status Raw: {status_raw}\n")
        idf.write(f"Last Active (UTC): {last_active}\n")
        idf.write(f"Deleted flag: {deleted_flag}\n\n")
        short_hash = profile_photo_sha
        if isinstance(profile_photo_sha, str) and len(profile_photo_sha) > 16 and profile_photo_sha not in ("no_photo", "not_available"):
            short_hash = f"{profile_photo_sha[:16]}..."

        idf.write("Profile Photo\n-------------\n")
        idf.write(f"Photo SHA256: {short_hash}\n")
        if short_hash != profile_photo_sha and profile_photo_sha not in ("no_photo", "not_available"):
            idf.write(f"Photo SHA256 (full): {profile_photo_sha}\n")
        idf.write(f"Photo Last Stored: {profile_photo_last_updated}\n\n")

    # If deleted flag is true → treat as deletion
    if deleted_flag:
        record_deletion("Flag: full_user.deleted == True", status_desc, last_active)
        await client.disconnect()
        return

    # ----------------------------------------------------------------
    # MEDIA HANDLING + ANCHOR ACQUISITION
    # ----------------------------------------------------------------
    log_info("Pulling media/messages from Telegram...")

    anchor_sha_cfg = cfg["target"].get("anchor_media_sha256")
    anchor_file_preserved = None
    message_samples = []
    anchor_status = "not_checked"
    media_records = []
    timeline_note = ""

    count = 0
    latest_anchor_found = None

    media_pull_error = None
    async for msg in client.iter_messages(user_entity, limit=media_limit):
        if msg.media:
            buffer = BytesIO()
            try:
                await client.download_media(msg, file=buffer)
            except (ConnectionError, asyncio.TimeoutError, OSError) as e:
                media_pull_error = f"media download interrupted: {e}"
                break
            except Exception:
                continue

            binary = buffer.getvalue()
            if not binary:
                continue

            sha = sha256_bytes(binary)

            file_info = getattr(msg, "file", None)
            file_name = getattr(file_info, "name", None) or ""
            file_ext = getattr(file_info, "ext", None) or ""
            mime = getattr(file_info, "mime_type", None) or ""
            size = getattr(file_info, "size", None) or len(binary)
            desc = file_name or file_ext or mime or msg.__class__.__name__

            media_records.append({
                "id": msg.id,
                "sha": sha,
                "desc": desc,
                "mime": mime,
                "size": size,
                "retained": False,
            })

            # First media encountered in this run = anchor candidate
            if latest_anchor_found is None:
                latest_anchor_found = {
                    "sha": sha,
                    "data": binary,
                    "ext": file_ext or ".bin",
                    "record_index": len(media_records) - 1,
                }

            count += 1

        text_raw = getattr(msg, "message", None) or ""
        text_content = text_raw.strip()
        if text_content and len(message_samples) < message_sample_limit:
            preview = text_content.replace("\n", " ")[:200]
            message_samples.append({
                "id": msg.id,
                "timestamp": fmt_utc(getattr(msg, "date", None)),
                "sha256": sha256_text(text_raw),
                "preview": preview
            })

        if text_raw and marker_targets:
            for marker in marker_targets:
                if marker_hits.get(marker["label"]):
                    continue
                if text_raw == marker["content"]:
                    marker_hits[marker["label"]] = {
                        "message_id": msg.id,
                        "timestamp": fmt_utc(getattr(msg, "date", None)),
                        "sha256": sha256_text(text_raw),
                        "body": text_raw,
                    }

    # Write acquisition summary
    with open(identity_path, "a", encoding="utf-8") as idf:
        idf.write("Media Acquisition\n-----------------\n")
        idf.write(f"Media files acquired: {count}\n")
        if count == 0:
            idf.write("WARNING: No media found — deletion likely.\n")

        idf.write("\nMessage Content Samples\n----------------------\n")
        if not message_samples:
            idf.write("No textual messages captured for sampling.\n")
        else:
            for idx, sample in enumerate(message_samples, 1):
                idf.write(f"[{idx}] Message ID: {sample['id']}\n")
                idf.write(f"    Timestamp: {sample['timestamp']}\n")
                idf.write(f"    Content SHA256: {sample['sha256']}\n")
                idf.write(f"    Preview: {sample['preview']}\n")

        idf.write("\nMedia Hashes (Not Retained)\n--------------------------\n")
        if not media_records:
            idf.write("No media retained or available this run.\n")
        else:
            for rec in media_records:
                retained_note = "anchor_preserved" if rec["retained"] else "not_retained"
                idf.write(f"Message ID: {rec['id']}\n")
                idf.write(f"    SHA256: {rec['sha']}\n")
                idf.write(f"    Descriptor: {rec['desc']}\n")
                idf.write(f"    MIME: {rec['mime']}\n")
                idf.write(f"    Size: {rec['size']} bytes\n")
                idf.write(f"    Retention: {retained_note}\n")
        if media_pull_error:
            idf.write(f"\nNOTE: {media_pull_error}\n")
            log_warning(media_pull_error)

        idf.write("\nConfigured Message Markers\n-------------------------\n")
        if not marker_targets:
            idf.write("No configured message markers.\n")
        else:
            for marker in marker_targets:
                hit = marker_hits.get(marker["label"])
                idf.write(f"{marker['label']}:\n")
                if hit:
                    idf.write(f"    Status: PRESENT\n")
                    idf.write(f"    Message ID: {hit['message_id']}\n")
                    idf.write(f"    Timestamp: {hit['timestamp']}\n")
                    idf.write(f"    Content SHA256: {hit['sha256']}\n")
                    idf.write("    Body:\n")
                    idf.write(f"        {hit['body']}\n")
                else:
                    idf.write("    Status: NOT FOUND\n")
                    idf.write(f"    Expected Content SHA256: {marker['expected_sha']}\n")

    with open(manifest_path, "w", encoding="utf-8") as mf:
        mf.write("# Media Hashes (not retained unless anchor)\n")
        if not media_records:
            mf.write("none\n")
        else:
            for rec in media_records:
                retained_note = "anchor_preserved" if rec["retained"] else "not_retained"
                descriptor = rec["desc"].replace("\n", " ")
                mf.write(
                    f"{rec['sha']}  message_id:{rec['id']} "
                    f"desc:{descriptor} mime:{rec['mime']} bytes:{rec['size']} "
                    f"{retained_note}\n"
                )
        mf.write("\n")

    if media_pull_error:
        timeline_note = media_pull_error

    # If no anchor exists yet → establish anchor
    if not anchor_sha_cfg:
        if latest_anchor_found:
            this_sha = latest_anchor_found["sha"]
            ext = latest_anchor_found["ext"] or ".bin"
            preserve_path = anchor_dir / f"anchor{ext}"
            preserve_path.write_bytes(latest_anchor_found["data"])
            idx = latest_anchor_found.get("record_index")
            if idx is not None and 0 <= idx < len(media_records):
                media_records[idx]["retained"] = True

            # Save anchor SHA to config
            cfg["target"]["anchor_media_sha256"] = this_sha
            save_config(cfg_path, cfg)

            with open(identity_path, "a", encoding="utf-8") as idf:
                idf.write("\nAnchor Media Established\n------------------------\n")
                idf.write(f"SHA256: {this_sha}\n")
            anchor_status = f"anchor established (sha={this_sha})"
            log_info(f"Anchor media established (SHA {this_sha}).")
        else:
            with open(identity_path, "a", encoding="utf-8") as idf:
                idf.write("\n[!] Cannot establish anchor — no media found.\n")
            anchor_status = "anchor_not_established_no_media"
            log_warning("Cannot establish anchor — no media found.")
    else:
        # Verify anchor
        expected_sha = anchor_sha_cfg
        preserve_file = next(anchor_dir.glob("anchor.*"), None)

        if not preserve_file:
            with open(identity_path, "a", encoding="utf-8") as idf:
                idf.write("\n[!] Anchor media missing — treat as deletion.\n")

            anchor_status = "anchor_missing"
            record_deletion("Reason: Anchor media missing", status_desc, last_active)
            await client.disconnect()
            return

        else:
            actual_sha = sha256_file(preserve_file)

            with open(identity_path, "a", encoding="utf-8") as idf:
                idf.write("\nAnchor Verification\n-------------------\n")
                idf.write(f"Expected SHA256: {expected_sha}\n")
                idf.write(f"Current SHA256:  {actual_sha}\n")
                if actual_sha != expected_sha:
                    idf.write("WARNING: Anchor mismatch — possible deletion or tampering.\n")
                    anchor_status = f"anchor_mismatch expected={expected_sha} current={actual_sha}"
                    log_warning("Anchor mismatch detected! Expected "
                                f"{expected_sha}, got {actual_sha}.")
                else:
                    anchor_status = "anchor_verified"
                    log_info("Anchor verification successful.")

    # ----------------------------------------------------------------
    # TIMELINE + FINALIZE RUN ARTIFACTS
    # ----------------------------------------------------------------
    if not deletion_triggered:
        append_day_identity_log()
        append_timeline_entry(status_desc, last_active, False, timeline_note)
    identity_sha = sha256_file(identity_path)
    rel_identity = identity_path.relative_to(run_dir)
    with open(manifest_path, "a", encoding="utf-8") as mf:
        mf.write("\n# Identity Document\n")
        mf.write(f"{identity_sha}  {rel_identity}\n")

    manifest_sha = sha256_file(manifest_path)

    audit_report_path = run_dir / "audit_report.txt"
    marker_present = sum(1 for hit in marker_hits.values() if hit)
    marker_total = len(marker_targets)
    with open(audit_report_path, "w", encoding="utf-8") as ar:
        ar.write("AUDIT RUN REPORT\n")
        ar.write("=================\n\n")
        ar.write(f"Run Timestamp (UTC): {stamp}\n")
        ar.write(f"Config SHA256: {config_sha}\n")
        ar.write(f"Session SHA256: {session_sha}\n")
        ar.write(f"Identity SHA256: {identity_sha}\n")
        ar.write(f"Manifest SHA256: {manifest_sha}\n")
        ar.write(f"Media Files: {count}\n")
        ar.write(f"Message Samples Recorded: {len(message_samples)}\n")
        ar.write(f"Marker Hits: {marker_present}/{marker_total}\n")
        ar.write(f"Profile Photo SHA256: {profile_photo_sha}\n")
        ar.write(f"Profile Photo Last Stored: {profile_photo_last_updated}\n")
        ar.write(f"Anchor Status: {anchor_status}\n")
        ar.write("\nMarker Details\n--------------\n")
        if not marker_targets:
            ar.write("No markers configured.\n")
        else:
            for marker in marker_targets:
                hit = marker_hits.get(marker["label"])
                if hit:
                    ar.write(f"{marker['label']}: PRESENT at {hit['timestamp']} (id={hit['message_id']})\n")
                else:
                    ar.write(f"{marker['label']}: NOT FOUND\n")

    audit_report_sha = sha256_file(audit_report_path)
    audit_sha_path = audit_report_path.with_suffix(audit_report_path.suffix + ".sha256")
    audit_sha_path.write_text(audit_report_sha, encoding="utf-8")

    rel_manifest = manifest_path.relative_to(target_dir)
    rel_audit = audit_report_path.relative_to(target_dir)
    rel_identity_target = identity_path.relative_to(target_dir)
    with open(date_master_manifest_path, "a", encoding="utf-8") as mm:
        mm.write(f"Run: {stamp}\n")
        mm.write(f"  Identity: {rel_identity_target} ({identity_sha})\n")
        mm.write(f"  Manifest: {rel_manifest} ({manifest_sha})\n")
        mm.write(f"  Audit Report: {rel_audit} ({audit_report_sha})\n")
        mm.write(f"  Config SHA256: {config_sha}\n")
        mm.write(f"  Session SHA256: {session_sha}\n")
        mm.write(f"  Profile Photo SHA256: {profile_photo_sha}\n")
        mm.write("\n")

    await client.disconnect()
    log_info("Audit complete.")


# -------------------------------------------------------------------
# Entrypoint
# -------------------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log_warning("Interrupted by user.")

# END OF PYTHON SCRIPT
