# OpenServerDesk 0.6.48 — Qui+PostgreSQL cold-data checkpoint and restore verification

PostgreSQL needs stronger evidence than SQLite PRAGMA quick_check. For exact original CasaOS Qui 1.28.0 + PostgreSQL 16 Alpine staging project:

- Backup quiesces dependent Qui, then PostgreSQL (reverse DAG), before creating the volume snapshot.
- A snapshot is archived only after PostgreSQL 16 PG_VERSION, 8192-byte pg_control and absence of postmaster.pid are checked, and a PostgreSQL 16 pg_controldata process reports "Database cluster state: shut down".
- The pg_controldata process runs from the exact immutable image SHA already assigned to the stage PostgreSQL container, in an ephemeral Docker --network none --read-only --cap-drop ALL sandbox. The read-only inspector runs UID0 because retained checkpoint archive files are root-owned mode 0600; this grants no writeable mounts, host privileges or network access. The only mounted source is the validated stage-owned PostgreSQL directory, read-only. It never accesses CasaOS or external Nextcloud data.
- Snapshot manifest schema v4 marks postgresql_cold_verified=true and retains the full stage-file SHA-256 digest. Prior v3 SQLite backups remain valid for MySpeed. The exact Qui app refuses missing or downgrade v4 PostgreSQL evidence.
- Restore validates the existing archive, records the undo snapshot, restores all stage volumes while the verified services are stopped, hashes restored contents, runs pg_controldata again against the restored stage database and then restarts PostgreSQL followed by Qui with health gates.
- Failed validation leaves the explicit restore journal rather than silently claiming success. This proves offline physical shutdown consistency, not query-level or distributed transactional correctness.
- No production Compose mutation, no external HDD mount, and no automatic cleanup of an operator's original backup. Production replacement remains prohibited.

## Authentic UAT progression (19 Oct 2026)
- Initial v0.6.48 backup failed on copied root-owned snapshot: UID1000 inspector could not read 0600 pg_control. Transaction journal retained; recover-online restored both running services and Qui HTTP 200.
- The actual PostgreSQL staging database was clean when stopped, as checked by pg_controldata against the original live volume. Fixed verifier owner handling in v0.6.49 and v0.6.51.
- v0.6.49 cold backup subsequently succeeded: checkpoint data-e235e63d9043, PostgreSQL physical shutdown evidence true, both service healthchecks healthy after restart.
- Subsequent restore required quota and mixed archive/live UID fixes in v0.6.50 and v0.6.51. This document does not claim the earlier failed attempts passed.
