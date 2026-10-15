# OpenServerDesk M1 — complete cold-backup integrity hardening

The earlier verifier checked only files already mentioned in a backup
manifest. Unlisted files and permissions/ACL changes could remain invisible.

The cold-backup engine now checks every file and directory, rejects unexpected
entries/sources and special files, verifies SHA256/size, ownership, mode,
nanosecond mtime, POSIX ACL/extended-attribute SHA256, and internal hardlink
relationships. It rejects absolute or escaping symlinks and hardlinks to
unrepresented inodes outside a single backup source.

Before each copy, the original data tree is validated. The copied archive
must match every original entry and its recoverable metadata, and the original
is scanned again after copying to detect concurrent writes. Restoring is
strictly to a new private staging root; it is reverified before publication.

Authentic disposable SQLite/Compose filesystem UAT recorded:
- EXTRA_FILES_PERMISSION_AND_XATTR_TAMPER_REJECTED_PASS
- EXTERNAL_SYMLINK_DEPENDENCY_FAIL_CLOSED_PASS
- INTERNAL_HARDLINK_FIDELITY_AND_EXTERNAL_LINK_REJECTION_PASS
- REAL_TWO_SOURCE_SQLITE_AND_COMPOSE_COLD_BACKUP_RESTORE_PASS
- RESTORE_NEW_TREE_WITH_UNTOUCHED_LIVE_ORIGINAL_PASS
- BACKUP_INTEGRITY_TAMPER_REJECTION_PASS
- LIVE_DOCKER_WRITERS_BACKUP_FAIL_CLOSED_PASS

The source code remains FAIL-CLOSED while any real Docker workload runs.
The demonstration does not authorize a live backup, production cutover or
claim full consistency of all 40 real bind/Compose source paths. Other writers,
disk capacity, real restore+service startup, full upstream integration,
production-equivalent rollback, signing and security approval remain blocked.
