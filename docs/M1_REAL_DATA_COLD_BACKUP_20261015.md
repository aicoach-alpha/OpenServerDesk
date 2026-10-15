# Real data preservation: cold backup + staged full-tree recovery

New in v0.6.7: tools/migration/m1_cold_backup.py, included in the
staging candidate without any postinstall or production activation hook.

Production current state (2026-10-15 18:36 WIB):
Fresh Docker inspection found 16 running containers, 10 Compose projects,
30 bind sources, 10 Compose configuration files, hence 40 backup
sources over three filesystems. Twenty-five live mounts are writable.
Read-only plan mode correctly reported cold_backup_authorized=false.

The cold backup engine is not authorization to stop anything: It REFUSES
while any discovered Docker container is running or any writable mount is live.
It never stops, restarts, creates or deletes Docker containers, networks,
CasaOS production services or source paths.

When cold/quiesced, the tool reads all bind sources and Compose definitions,
rejects missing/symlink roots, unsupported nested mounts, insufficient disk
space and unknown inventory, and copies source trees using cp -a. It preserves
metadata, writes per-entry SHA256 hashes and a root-private manifest, and
publishes the complete backup atomically in staging cold-backups. Verify
detects corruption. Restore makes a *separate* verified new recovery tree
in root-private staging cold-recovery; it never overwrites source paths.

One targeted end-to-end disposable data rehearsal proved:
REAL_TWO_SOURCE_SQLITE_AND_COMPOSE_COLD_BACKUP_RESTORE_PASS,
RESTORE_NEW_TREE_WITH_UNTOUCHED_LIVE_ORIGINAL_PASS,
BACKUP_INTEGRITY_TAMPER_REJECTION_PASS,
LIVE_DOCKER_WRITERS_BACKUP_FAIL_CLOSED_PASS.

This does NOT establish FULL production consistency. Remaining mandatory
proof: user-approved maintenance period, quiescence of non-Docker writers,
actual full dataset capacity, all 40 real sources backed up and restored to
independent environment with service startup, ACL/xattr fidelity audit,
authenticated complete UI, safe in-place switch and automated rollback,
independent security acceptance and signed final release. No live source was
stopped or modified. migration_allowed remains false.
