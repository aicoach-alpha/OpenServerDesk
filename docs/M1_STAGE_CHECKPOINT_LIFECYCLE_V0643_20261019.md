# OpenServerDesk v0.6.43 — stage checkpoint cleanup lifecycle

The new online backup/restore workflow retains verified archives and undo snapshots. Each stage project is bounded to 4 snapshots, so operators now need safe and explicit deletion.

- Authenticated, write-authorized POST to compiled App Store with action delete-checkpoint, exact owned project and exact data checkpoint ID.
- Snapshot must be an on-disk, same-filesystem stage-owned archive with a valid manifest, SHA-256 tree digest and SQLite quick-check evidence.
- Reject deletion while update, restore-data, or online-data recovery journals exist.
- Delete only the selected stage archive; never the app's live bind volume, original CasaOS mounts, production Compose or external Nextcloud files.
- Dashboard includes explicit Delete backup action for each archive. Requires confirmation, no scheduled deletion or automatic retention.
- The upper bound remains 4 archives, and operators can remove their own old checkpoints to free capacity.
- Production cutover remains unauthorized and complete multi-service App Store parity unproven.
