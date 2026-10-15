# M1 focused configuration and application-volume restore — 2026-10-15

Scope: **one isolated staging fixture**, no real CasaOS or Docker volume changes.

Implementation: `tools/migration/volume_fixture.py` now provides
`restore(snapshot_dir, target, fixture_root)` with explicit scratch-root
containment and checksum verification before changing target content.
It restores a complete offline fixture tree by preparing a replacement and
swapping directories. File modes are copied from the snapshot; later files
are removed by full-tree replacement. This is not power-loss-atomic.

Focused integration:
- `tools/staging/verify-volume-config-recovery.py` creates a temporary
  config+volume fixture beneath `/opt/openserverdesk-dev/runtime-stage`.
- Snapshot captures Gateway config and synthetic app volume settings/state.
- Fixture configuration and volume contents are changed, a file is removed,
  and a new file is added.
- Restore recovers baseline settings/configuration and removed file, and
  removes the post-snapshot file. PASS.
- An isolated Docker Gateway container is started from the existing
  packaged real Gateway binary using the restored config. HTTP /ping PASS.
- Transient runtime/log directories are recreated separately; these are not
  part of the persistent snapshot.
- Existing three staging containers remain running; six CasaOS/Docker/
  OpenServerDesk systemd units remain active.

Not covered: running Docker named volumes, full filesystem permissions/xattrs,
concurrent writers, crash/power-loss interruption during directory swaps,
whole-application restart/rollback, production change, or final security audit.
Migration remains blocked.
