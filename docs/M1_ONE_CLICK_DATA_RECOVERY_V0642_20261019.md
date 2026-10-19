# OpenServerDesk 0.6.42 — automatic quiesced stage data backup/restore

New compiled App Store actions, all staging-only:

- backup-online: persist a journal of originally running stage-owned services; stop only their verified full container IDs; create a SHA256-verified, SQLite-quick-checked staging volume checkpoint; resume just the services that had been running and check readiness before clearing the journal.
- restore-online: validate the selected snapshot before changing anything, journal service state, stop only scoped containers, create and durably journal an undo checkpoint, restore the selected snapshot with post-copy integrity verification, and resume original service state. If interrupted at any step, preserve the transaction journal.
- recover-online: only for a pending online-data journal; stop verified staging-owned containers, restore the saved undo checkpoint when available, resume original service state and clear the journal only after success.
- Frontend shows Backup + restart, Restore + restart and Recover online. Existing manual checkpoint and restore remain available.
- A new online-data journal blocks conflicting staging actions until recovery. Original Docker production projects, CasaOS services and external Nextcloud HDD are never mounted or modified.
- The immutable image/config update and rollback actions are not yet automatically coupled to this transaction. They remain separate and must not be described as data-safe. Future work may integrate them after acceptance.
- This only proves isolated SQLite-capable stage-owned volume workflows, not a database cluster-consistent snapshot or production parity.
