#!/usr/bin/env python3
"""Cleanup per-day run folders when no deletion was detected."""
import argparse
import pathlib
import shutil

ALLOWED_FILES = {"day_summary.txt", "status_timeline.csv"}

def parse_day_summary(path: pathlib.Path):
    deleted = None
    status = ""
    note = ""
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lower().startswith("status:"):
            status = line.split(":", 1)[1].strip()
        elif line.lower().startswith("deleted flag:"):
            try:
                deleted = bool(int(line.split(":", 1)[1].strip()))
            except ValueError:
                deleted = None
        elif line.lower().startswith("note:"):
            note = line.split(":", 1)[1].strip()
    return {"deleted": deleted, "status": status, "note": note}


def cleanup_day(date_dir: pathlib.Path, dry_run: bool):
    summary = parse_day_summary(date_dir / "day_summary.txt")
    if not summary:
        return False, "missing day_summary.txt"
    if summary["deleted"]:
        return False, "deletion detected"
    if summary["status"].lower() in {"network_error", "unresolved"}:
        return False, f"status {summary['status']}"

    removed_items = []
    for item in date_dir.iterdir():
        if item.name in ALLOWED_FILES:
            continue
        if dry_run:
            removed_items.append(item.name)
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
        removed_items.append(item.name)
    return True, ", ".join(sorted(removed_items)) or "nothing to remove"


def main():
    parser = argparse.ArgumentParser(description="Cleanup daily run folders when account remained active.")
    parser.add_argument("--target-dir", required=True,
                        help="Path to targets/<uid> directory (must contain runs/).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be removed without deleting.")
    args = parser.parse_args()

    target_dir = pathlib.Path(args.target_dir).resolve()
    runs_dir = target_dir / "runs"
    if not runs_dir.is_dir():
        raise SystemExit(f"runs directory not found under {target_dir}")

    for date_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        success, info = cleanup_day(date_dir, args.dry_run)
        if success:
            action = "DRY-RUN would remove" if args.dry_run else "Removed"
            print(f"{action} artifacts for {date_dir.name}: {info}")
        else:
            print(f"Skipped {date_dir.name}: {info}")

if __name__ == "__main__":
    main()
