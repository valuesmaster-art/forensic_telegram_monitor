# Audit Report Interpretation

Each run produces `audit_report.txt` and `audit_report.txt.sha256`. The audit report condenses the run’s integrity metadata so you can quickly confirm evidence completeness.

## Structure
1. **Header block**
   - Run timestamp, config SHA-256, session SHA-256
   - SHA-256 for `identity.txt` and `manifest.txt` (cross-check against their contents)
   - Counts for media files processed and textual message samples logged
   - Marker hit ratio (`hits/total`)
   - Profile photo hash + “last stored” timestamp
   - Anchor status (established, verified, missing, or mismatch)

2. **Marker Details**
   - For each configured marker, shows either a PRESENT entry with timestamp/message ID or a NOT FOUND note. Use this to prove whether a crucial statement existed at audit time.

## Validating Integrity
1. Compute SHA-256 of `audit_report.txt` and compare with the `.sha256` sidecar.
2. Use the hashes listed in the report to verify `identity.txt` and `manifest.txt` have not changed.
3. Cross-reference the `Run Timestamp` with `status_timeline.csv` to see whether this was the run that detected deletion or confirmed continued activity.

## When Deletion Is Detected
If `audit_report.txt` lists `Anchor Status: anchor_missing` or notes a deletion reason, no further run folders are produced unless `--force-run` is used. The audit report therefore serves as the final evidential snapshot.

Keep the audit reports, master manifest, and status timeline together—they form the complete chain-of-custody for each interval.
