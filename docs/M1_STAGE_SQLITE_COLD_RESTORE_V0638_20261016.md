# OpenServerDesk v0.6.38 — isolated SQLite cold-restore integrity gate

Only stage-owned compiled App Store project volume roots are eligible.

- Checkpoints still require every project container stopped.
- New checkpoint manifest version 3 records checksums and how many SQLite files passed PRAGMA quick_check(1).
- SQLite files are detected by their SQLite file signature or .db/.sqlite/.sqlite3 filename. Mislabelled/corrupted database files are rejected.
- Nonempty SQLite rollback journals and WAL sidecars fail closed because a cold portable standalone database snapshot cannot be claimed with pending transactions.
- Before restoring, validate snapshot checksum and SQLite quick-check evidence.
- After restoring, compare the entire restored tree against the saved snapshot and repeat SQLite quick-check. Any failure retains the durable undo journal for recovery.
- The same post-restore checks run on interrupted-restore undo recovery.
- API responses include a count of verified SQLite files. database_integrity_verified remains false: this is NOT PostgreSQL, MySQL, application-level, or multi-service transaction-consistency proof.

Testing uses temporary staging-owned fixture directories and never touches production Compose volumes or external Nextcloud files. Full real App Store lifecycle UAT and production cutover authorization remain outstanding. M1 accepted scope remains 49%.
