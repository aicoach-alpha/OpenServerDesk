# M1 multi-project application data and Compose rollback — isolated staging

Feature: `tools/migration/full_app_recovery.py`, bundled in the v0.6.2
staging-only Debian candidate alongside its `volume_fixture.py` dependency.

This is the first coordinated **multi-project application backup → corruption
→ restored application startup** using actual Docker Engine containers, rather
than a single mock file. Snapshot and restore operate on a
strictly constrained disposable OpenServerDesk staging fixture, never on
CasaOS production mounts. A unique fixture owner token is verified and
Docker must confirm no running containers with its scoped owner label.
If a staged writer remains active or Docker inspection fails, the backup
or restore is rejected. Both source and replacement trees are preserved:
restoration atomically publishes a separate recovered directory, rather than
overwriting the original project data.

An integrated scenario in
`tools/staging/verify-real-multiproject-recovery.py` covered **two Docker
application projects**, real SQLite state, two Compose definitions and a bind
source containing JSON data. It observed all of:

- `LIVE_STAGE_WRITER_QUIESCENCE_ENFORCED_PASS`: a still-running explicitly
  labeled stage application prevented the snapshot.
- Both applications stopped, exact per-file SHA256/size/mode manifest copied
  and verified, original SQLite value then deliberately changed and a second
  source deleted.
- A separate, verified restore returned the original SQLite row, Compose
  definitions and JSON value, then a new network-disabled Docker container
  successfully read the recovered bind source.
- `TWO_REAL_DOCKER_APP_PROJECTS_QUIESCE_BACKUP_RESTORE_AND_BOOT_PASS`.
- `RECOVERED_SQLITE_COMPOSE_AND_EXTERNAL_BIND_DATA_PASS`.
- `PRODUCTION_MODIFIED_FALSE`.

The functional scope is **staging only**. It still cannot serve as a real
CasaOS data migration because this tool requires staging root ownership;
production has 30 separate live bind sources, 25 writable mounts and many
service-specific consistency needs. Complete on-host inventory, independent
signed production release, authenticated UI, a full service cutover/
automated rollback coordinator and scoped penetration testing remain
separate mandatory release gates. Migration remains disallowed.
