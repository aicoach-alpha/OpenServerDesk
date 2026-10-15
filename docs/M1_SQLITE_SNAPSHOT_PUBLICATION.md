# M1 SQLite snapshot safe publication — 2026-10-15

The fixture-only SQLite snapshot helper now stages database backup into a
temporary file in the destination directory. The snapshot is integrity checked
and fsynced before publishing with hard-link creation that refuses an already
existing destination. The parent directory is fsynced. The staging file is
removed even if the backup fails.

Fault injection before SQLite backup proves no destination or staged file is
left behind. Full Python test suite: 38 PASS.

Limitations: not power-loss-certified; fsync and link failure modes under
storage faults need realistic fault injection. No live-service quiescence,
complete app-volume restore, or production-equivalent package rollback is
implemented. Do not unlock production migration.
