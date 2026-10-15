# M1 SQLite snapshot symlink hardening — 2026-10-15

Fixed an input validation weakness in the fixture-only SQLite snapshot
helper: source and destination paths are now checked for direct symlinks
before canonicalization. Previously canonicalization erased the evidence
that the input itself was a symlink.

New tests verify that linked sources are denied without creating a backup,
and linked destinations are denied without overwriting the link target.
Full Python suite: 37 tests PASS.

Limitations: this does not eliminate all TOCTOU races, protect every
symlinked ancestor, or validate live host backup safety. No production
database was touched. The staging migration readiness gate remains closed.
