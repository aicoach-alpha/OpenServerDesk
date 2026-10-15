# M1 real Docker bind migration topology

Read-only inspection of the existing private Docker inventory. No app
contents were read, copied, stopped, or rewritten.

At 2026-10-15 18:34 WIB: 30 unique bind sources, 25 directories and
5 files, across 3 filesystems. 25 writable bind consumers; two sources
have multiple writable consumers. Zero nested source pairs and zero
special source types. Two shared writable sources require coordinated
writer shutdown and consistent snapshots.

The API exposes counts only. Raw source paths remain in a private local
report, not published to GitHub or exposed via HTTP. Production migration
and rollback have NOT been proven; migration_allowed stays false.
