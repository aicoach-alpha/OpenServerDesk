# CasaOS platform-only real SSD backup and staging restore — 16 Oct 2026

Development implemented and verified directly on andre-nas without
stopping CasaOS, changing Docker containers or touching Nextcloud uploads.

- Program: tools/migration/m1_config_recovery.py.
- Allowed source selection: m1_platform_scope.select() over safe platform
  configuration roots and selected Compose YAML definitions. No paths from
  /mnt/data, protected Nextcloud user upload directories, Docker volumes,
  raw user bind contents, Docker image layers or full external HDD.
- Backup output: root-private 0700 directory on existing SSD
  /mnt/ssd-turbo/openserverdesk-m1-platform-config-backups. The chosen SSD
  is mounted as /dev/sda1, separate from root /dev/sdb2. Only the dedicated
  new OpenServerDesk folder on the SSD is created or written.
- Actual real-platform backup id: config-a24c34bb34e6df6d.
  4 deduplicated source groups from 13 safe selected references,
  1652 file entries verified, 3 SQLite databases passed integrity check.
  Backup manifest SHA256:
  9ff001aa1823d4c22ce0e3e9764be57acfff57e541a68720e1af0cb4169445da.
- Actual fresh independent staging restoration on the SSD verified all
  1652 files, all 3 SQLite databases. The original CasaOS configuration
  was NOT overwritten or changed. The SSD backup is private and contains
  configuration/credentials: NEVER expose its contents via HTTP or GitHub.
- Fail-closed safeguards: all protected Nextcloud/HDD paths excluded
  lexically BEFORE file metadata access; no walking nested mounts; no
  symlink dereference (only link text is preserved); source-copy hash checks;
  SQLite transaction-aware per-database backup; exact file/owner/mode/
  checksum validation; root-private independent SSD; no archive overwrite;
  restored tree is a NEW directory and cannot overwrite the real root.
- Fixture proof also verified SQLite state, symbolic links and independent
  recovery; tampered backup rejects verification.
- Source metadata inventory: 16 containers/10 Compose project references,
  four protected bind references skipped; those paths remain in Docker and
  are never moved or opened by this backup.
- LIMITATION: backed up while production applications were online, so
  individual SQLite snapshots are consistent, but one cross-service
  transactionally atomic snapshot is NOT proven. Restore is staging-only,
  not a real release rollback or production cutover. Signed production
  deployment/security acceptance still outstanding. migration_allowed
  remains false.
