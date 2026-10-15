# M1 rollback serialization and SQLite sidecar gate — 2026-10-15

The fixture-only journaled recovery prototype now uses a per-target
advisory flock held throughout replace_pair and recover. A second process
attempting rollback on the locked target fails closed, without changing
fixture contents. The lock file is retained, not unlinked, avoiding an
obvious lock inode race.

It also refuses operations if user.db-wal, user.db-shm or user.db-journal
exist in the relevant fixture directories. The rejection is intentionally
conservative: a running database service must be stopped and SQLite safely
checkpointed before proceeding. Detection alone does not guarantee a
consistent backup, and absence of sidecars does not guarantee no writer.

Tests include a real subprocess contention check and simulated WAL file
rejection. Full Python test suite: 29 tests PASS.

Remaining blockers: no live service quiescence mechanism, SQLite online
backup/checkpoint integration with this journal, crash-safe journal cleanup,
disk-full/power-loss assurance, application volume coverage or M1 pentest.
Production migration remains prohibited.
