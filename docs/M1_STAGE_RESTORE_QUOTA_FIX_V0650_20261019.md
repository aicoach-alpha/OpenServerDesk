# OpenServerDesk v0.6.50 — PostgreSQL restore quota and recovery

Authentic v0.6.49 stage-only PostgreSQL cold backup PASS: checkpoint data-e235e63d9043 and both Qui/PostgreSQL healthy. The subsequent restore failed before copying data because _apply mistakenly accumulated source archive bytes AND current destination bytes into one 128MiB quota. The application had 67MB on each side, so two individually allowed datasets exceeded the one shared counter.

Fix _apply to maintain independent source_quota and destination_quota while preserving the 128MiB and 12,000-file constraints for each entire dataset across all service volumes. Continue to validate snapshots, SHA-256 and cold PostgreSQL pg_controldata before and after restore. New focused regression creates two 6-byte datasets with an 8-byte per-dataset limit; old code would incorrectly reject 12 total.

The v0.6.49 failed restore left a durable undo journal, preserved both snapshots and stopped the verified Qui/PostgreSQL staging containers, with no preflight file modification. Once deployed, use recover-online to restore undo and service health, then a single end-to-end actual restore from the good checkpoint. No production operations or Nextcloud HDD access. No cutover authorized.

## Authentic recovery observation
- First v0.6.50 restore recovery progressed beyond source/destination size checks, copying 67MB PostgreSQL data back to its stage volume; restored source/destination SHA-256 trees matched.
- The root-owned archive inspector still ran UID0, unable to read post-restore UID1000-owned pg_control because cap_drop ALL intentionally removes DAC bypass. This left the recovery journal and stopped app intact.
- The separate UID-aware correction is implemented in v0.6.51, not retrospectively claimed as a 0.6.50 PASS.
