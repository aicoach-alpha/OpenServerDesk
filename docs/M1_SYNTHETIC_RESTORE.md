# M1 synthetic snapshot recovery rehearsal — 2026-10-15

A focused fixture creates CasaOS-like configuration files, a compose
definition and a SQLite user table, all under a disposable temporary
directory. It creates a backup, intentionally changes the original config
and deletes the fixture user's row, and verifies the **archive** still
contains the original config and SQLite row. The rehearsal validates
archive manifest digests and SQLite integrity without writing into the
original directory or any live CasaOS path.

The first run detected a real coverage flaw: `rehearse()` checked SQLite
only at the hard-coded production layout, missing synthetic relocation
fixtures. Fixed by checking all manifest-listed `.db` files.

Post-fix result: **20/20 unit and integration tests PASS**. Staging API
responded healthy and six production/system services were active.

Scope limitation: this proves isolated backup snapshot content and
checksum/integrity validation. It does **not** prove service activation,
running container recovery, persistent volumes, real host upgrade, or
automatic transactional rollback. Migration remains denied in staging.
