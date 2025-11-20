# Identity Report Interpretation

`identity.txt` acts as the human-readable evidential summary for a single run. Each section has a specific purpose, so review it top-to-bottom to reconstruct the state that was observed.

## 1. Header + Target Identifiers
- **Run Timestamp (UTC)** – trust anchor for correlating with other evidence.
- **Config & Session SHA256** – prove the inputs and authenticated session used for this run.
- **Target identifiers** – confirms UID, username, phone, and address book label targeted.

## 2. Identity Details
- **Name/Username/Phone** – values returned by Telethon; blank/unknown can signal deletion.
- **Status / Status Raw / Last Active** – descriptive status string, the raw Telethon class, and the last-seen timestamp (when Telegram exposes it).
- **Deleted flag** – if `True` the run exits immediately; check `status_timeline.csv` for chronology.
- **Profile Photo** – current hash (truncated + full) and the last time that hash was stored. If the hash changed, `profile_photos/profile_<sha>.ext` holds the canonical copy.

## 3. Media Acquisition
- **Media files acquired** – count of Telegram messages with media payloads during this run. `WARNING` appears if no media were visible (possible deletion or no new media).
- **Message Content Samples** – up to `message_sample_count` textual messages (ID, timestamp, hash, preview) to prove conversational context.
- **Media Hashes (Not Retained)** – SHA-256, descriptor, MIME, size, and retention info for every media message. Only the anchor media is retained; all other hashes exist purely in the logs.

## 4. Configured Message Markers
- Each marker is listed with its presence status. When present, the log includes message ID, timestamp, hash, and the full body; when absent it shows the expected hash to prove what was searched for.

Use `identity.txt` together with `audit_report.txt` and `status_timeline.csv` to establish when the target was last active, whether key evidence was visible, and which hashes correspond to captured materials.
