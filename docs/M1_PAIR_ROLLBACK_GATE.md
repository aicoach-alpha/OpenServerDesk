# M1 offline binary + SQLite pair rollback prototype — 2026-10-15

Added `tools/migration/atomic_pair_rollback.py` as a **fixture-only**
recovery prototype, requiring a manifest with exactly two checksum-protected
members: `userservice` and `user.db`. No host/system paths or CasaOS
services are changed by this tool.

Tested:
- Snapshot-integrity verification and successful restoration of the pair.
- Tampered snapshot rejected before changes.
- Injected Python exception between two replacement operations restores
  the previous fixture pair.

Full Python test suite: 23 tests PASS.

Important limitation: despite the prototype filename, two `os.replace()`
operations are not atomically committed as one transaction. Recovery uses an
in-process exception handler and memory snapshots, so it is NOT robust
against SIGKILL, kernel crash, power loss, disk-full conditions, or
concurrent readers. It also does not coordinate actual service stoppage,
schema migrations, filesystem syncing, config files, persistent volumes,
or crash-safe transaction journals. Never use this prototype on production.
M1 is still blocked pending a crash-safe staged recovery protocol and audit.
