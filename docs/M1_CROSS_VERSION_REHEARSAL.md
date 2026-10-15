# M1 UserService cross-version activation and database rollback — 2026-10-15

Pinned real upstream source versions:
- ReCasaOS UserService v0.4.30 at ab56332, built in a separate immutable-source workspace.
- ReCasaOS UserService v0.4.31 at 576c2a0, known-good staging binary.
Different binary checksums verified. The v0.4.30 offline Go test suite and build passed.

Performed only in Docker staging Gateway network namespace (the Gateway's
network mode is none), using a NEW independent SQLite directory and synthetic
credentials. Existing staging UserService was stopped temporarily.

1. Start actual v0.4.30 UserService with fresh fixture DB; synthetic
   registration/login: PASS.
2. Snapshot the v0.4.30 fixture DB; stop/remove the v0.4.30 container.
3. Start actual v0.4.31 UserService on the same fixture DB; login: PASS.
4. Stop/remove v0.4.31; restore the pre-upgrade DB snapshot.
5. Start actual v0.4.30 binary on the restored DB; login: PASS.
6. Remove the disposable candidate and ephemeral credentials, restart the
   original staged UserService, verify its API and Message Bus reconnect: PASS.
7. All six required production/staging systemd units remained active.

**PASS:** physical real-version v0.4.30 to v0.4.31 activation, account
authentication on upgraded fixture, and coordinated rollback of binary
and pre-upgrade synthetic SQLite snapshot. Original staging restored.

**NOT YET PASS:** rollback using a post-upgrade Argon2id DB without restoring
the snapshot, complete application/Compose volume migration, transactional
activation on an existing CasaOS deployment, crash-consistent recovery,
end-to-end in-place upgrade, or M1 security audit/pentest. Never interpret
this rehearsal as permission for production migration.
