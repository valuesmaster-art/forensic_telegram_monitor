# Telegram Identity Monitoring Tool — Forensic Overview

## Simple Overview (Plain English)

1. **What the tool does** – It keeps an eye on a specific Telegram account and takes a time‑stamped “snapshot” every time it runs. Each snapshot records who the account appears to belong to, what messages and media were visible, and whether the account looked normal or deleted.
2. **How it proves nothing was deleted** – For important text messages you care about, you can register “markers.” The script looks for those exact texts and logs (a) a copy of the words, (b) the time they were visible, and (c) a SHA‑256 fingerprint. If the text disappears later, you have proof it was there before.  
   For photos or other shared media, it stores the SHA‑256 hash — a unique digital fingerprint — so you can prove that the sender’s photo or file is the same one shared between the parties.
3. **What happens if the account vanishes** – As soon as Telegram reports the account is deleted (or the anchor media/proof disappears), the tool writes a deletion report and stops running. Every day also gets its own summary file so you can see exactly when the account went offline.
4. **Why it’s safe** – Apart from the anchor photo and current profile picture (needed to prove the account’s identity), the tool does not keep media files. It records hashes instead, so you retain proof without storing sensitive content.

If you need the full technical details, read the sections below or refer to `docs/identity_report.md` and `docs/audit_report.md`.

---

## Technical Highlights

### 1. Chain of Custody
- Daily folders live under `targets/<uid>/runs/YYYYMMDD/`. Each run inside has `identity.txt`, `manifest.txt`, `audit_report.txt`, and hashed references.  
- SHA‑256 values are written into the manifest, audit report, day-level master manifest, and optional `.sha256` sidecars (e.g., `audit_report.txt.sha256`).  
- `runs/<date>/master_manifest.txt` lists every run that occurred that day, with hashes for identity/manifest/audit files. The per-day `day_identity_log.txt` keeps the full narrative from each `identity.txt`, ensuring evidence survives even after cleanup of older run folders.

### 2. Identity & Media Assurance
- Each run captures UID, username, phone, status, last-active time, anchor hash, and the current profile photo hash.  
- The first media ever seen becomes the “anchor” and is stored once; later runs re-check its hash.  
- Profile photos are saved under `profile_<sha>.ext` with hashed sidecars and optional EXIF timestamps.

### 3. Message Markers & Media Hashing
- Operators can declare exact message texts that are critical to the investigation. When those texts are present, the tool records message ID, timestamp, full body, and SHA‑256. That proves specific statements still existed at that time.  
- All media (photos, documents, voice notes) are downloaded in memory, hashed, and immediately discarded. Only the hash, MIME type, and size are logged — unless the media is the anchor or a profile photo. This lets you confirm the sender’s photo or shared file matches what the other party received.

### 4. Deletion Detection & Timeline
- Deletion triggers include Telethon RPC errors, `.deleted` flag, missing anchor media, or empty identity fields.  
- `runs/<date>/status_timeline.csv` captures every run’s timestamp, status, last active time, and reason (including network errors).  
- `runs/<date>/day_summary.txt` shows the latest status for that day at a glance.  
- When the day ends with the account still active, cleanup tools can remove older run folders but keep the final run plus all summaries (timeline, master manifest, identity log).

### 5. Audit-Ready Reporting
- `identity.txt` gives the narrative detail: identity data, markers, message samples, media hashes, and anchor/profile status.  
- `audit_report.txt` summarizes the run’s checksums, counts, anchor verification, and marker hits.  
- `docs/identity_report.md` and `docs/audit_report.md` describe how to read those files. Use them alongside `day_identity_log.txt` if older run folders were cleaned up.

## Presenting in Court

1. **Authenticate artifacts**  
   - Show the relevant `runs/<date>/master_manifest.txt`, recalc hashes for the referenced identity/manifest/audit files, and match against recorded SHA‑256 values.  
   - If cleanup was used, reference `day_identity_log.txt` for the preserved identity narratives.

2. **Explain the timeline**  
   - Use `status_timeline.csv` and `day_summary.txt` to demonstrate when the account was last active versus when deletion was detected.  
   - Cross-reference the specific run’s `audit_report.txt` to show the conditions that led to a deletion finding (e.g., RPC error, missing anchor).

3. **Prove message/media presence**  
   - Cite the marker entries in `identity.txt` (or `day_identity_log.txt`) showing the message body, timestamp, and SHA‑256.  
   - For shared media, present the recorded hash and descriptor (message ID, MIME, size) to prove the media matched what the user shared.

4. **Demonstrate deletion**  
   - Introduce `account_deleted.txt` along with the final `identity.txt`/`audit_report.txt` and show there are no runs afterward unless `--force-run` was explicitly used.

This structure lets you tell a straightforward forensic story: **what was visible, when it was visible, and exactly when it disappeared.**
