# v0.6.36 - Staging volume checkpoints and interrupted restore undo

Implements operator-triggered checkpoint, restore-data, and recover-data for
compiled stage-owned app volumes. It does not access CasaOS production volumes,
Nextcloud user-upload files, or external HDDs.

- Only explicit osd-compiled stage projects and exact manifest volume sources.
- Docker ownership and actual full container IDs validated before operations.
- Every service must be stopped for checkpoint, restore, or undo.
- Root-owned private checkpoint directories on the staging SSD.
- Reject symlinks, hard links, special files, and cross-device submounts.
- 128 MiB / 12,000 entries maximum per checkpoint; 4 checkpoint maximum.
- Durable undo snapshot and fsynced journal before restoring.
- Restore refuses to run if pending recovery exists; recover-data replays undo.
- New sandbox bind roots belong to UID/GID 1000 matching the fixed runtime UID.
- Manual restore is distinct from image/config rollback; no transaction-level DB integrity verification.

Fixture UAT proves snapshot/restore/recover and safety rejection without Docker.
Authentic Docker app-store e2e and database integrity checks are pending; this
is not general CasaOS parity or an authorized production cutover.
Acceptance progress 49%, migration_allowed false, no automatic monitor started.
