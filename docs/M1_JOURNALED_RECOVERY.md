# M1 journaled fixture-only recovery — 2026-10-15

Added `tools/migration/journaled_pair.py`, a separate offline prototype
with a persistent undo journal that contains checksummed copies of the
pre-replacement binary and SQLite database. The tool fsyncs file copies,
the journal manifest and relevant directories before replacing files.

Tests validated:
- Restoring previous pair after a completed replacement.
- Abrupt subprocess exit (`os._exit(71)`) immediately after replacing the
  first file, followed by successful recovery from a new process.
- A corrupted undo journal causes recovery to refuse operation.

Total project Python tests: **26 PASS**.

**Not production-ready.** Creation of the undo journal is not itself
transactional; a crash during journal creation or cleanup can strand a
partially written journal. There is no process/service quiescence guarantee,
lock against multiple writers, WAL checkpoint handling, volume/Compose
or configuration coverage, disk-full recovery, or demonstrated power-loss
durability. The test process-exit injection is not a host crash.
This prototype must not be run against live CasaOS paths and does not enable
real migration. M1 security audit and full service/volume rollback remain open.
