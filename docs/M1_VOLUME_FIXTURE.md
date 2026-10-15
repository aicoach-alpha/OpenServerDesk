# M1 isolated application-volume fixture gate — 2026-10-15

Added fixture-only volume snapshot and SHA-256 manifest validation in
`tools/migration/volume_fixture.py`. Tests cover nested config/data files,
source mutation after snapshot, snapshot corruption rejection, and symlink
escape rejection. Full Python suite: 34 PASS.

This does not snapshot live Docker named volumes, include permissions/xattrs,
preserve consistency with live database writes, restore Compose applications,
or provide a full migration rollback. No production volume was accessed.
Production activation remains blocked by migrate_installer.gate() and
/api/v1/migration/readiness. Real M1 pentest is still pending.
