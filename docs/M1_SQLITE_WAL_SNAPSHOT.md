# M1 WAL-mode SQLite snapshot gate — 2026-10-15

Added fixture-only `tools/migration/sqlite_fixture_snapshot.py` using
SQLite's online backup API rather than copying a possibly incomplete main
database file. Tests create a WAL-enabled SQLite fixture, insert and commit
a row, build a distinct snapshot and verify the row and integrity. Same-path
source/destination are rejected.

The full project Python test suite passed: 31 tests.

Limitations: this helper is not wired to the journaled binary rollback or
running ReCasaOS service lifecycle. Filesystem permission, hard links,
simultaneous writers during upgrade, disk-full, power loss and actual app
volumes remain unverified. The production migration gate remains closed.
