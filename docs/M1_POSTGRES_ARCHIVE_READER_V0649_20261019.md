# OpenServerDesk v0.6.49 — read-only root-owned archive inspection correction

Authentic initial v0.6.48 Qui PostgreSQL backup was rejected by the newly added cold verifier. Diagnosis:
- Both Qui and PostgreSQL were cleanly stopped; stage PG_VERSION=16, pg_control=8192 bytes, postmaster.pid absent and pg_controldata against original staging data returned clean shutdown, exit 0.
- Archive file copying produces mode-0600 root-owned copies of pg_control. The verifier's UID1000 was unable to read this archived file. This is a snapshot-owner mismatch, not a corrupted database.
- v0.6.49 executes only the pg_controldata reader as UID0, still in an ephemeral container with no network, immutable image ID, read-only rootfs, no Docker capabilities, no-new-privileges, strict memory/PID limits and a single read-only stage-owned archive mount.
- All actual application containers remain 1000:1000 with cap_drop ALL, no production mount.
- On the failed v0.6.48 backup, the durable recovery journal was retained and was recovered using recover-online; both actual Qui and Postgres returned healthy, and Qui served HTTP 200.
- This correction only changes the archive verifier. Full successful v0.6.49 backup/restore evidence must be gathered after deployment.
