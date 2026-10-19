# OpenServerDesk v0.6.51 — owner-aware offline PostgreSQL verifier

Actual v0.6.50 recovery copied the root-owned snapshot into stage PostgreSQL volume correctly: source and destination SHA-256 tree digests matched. The PostgreSQL offline validator then refused the restored copy because it ran UID0 with all capabilities dropped and therefore could not read 0600 pg_control that restore chowned back to UID1000. The transaction journal remained and stage containers were held stopped.

The new verifier derives the read-only inspector UID/GID from the verified pg_control owner. Only (0,0) for archived copies or (1000,1000) for restored stage data are permitted. Any mixed or foreign control owner fails closed. Container sandbox constraints remain: no network, immutable image SHA, read-only rootfs, no capabilities, no-new-privileges, limited PIDs and RAM, and exactly one read-only mount inside the stage-owned project.

No CasaOS production or external Nextcloud HDD access. Perform recover-online with this correction, then authentic PostgreSQL cold backup/restore and HTTP service verification.

## Authentic v0.6.51 end-to-end staging UAT
- New owner-aware verifier passed 2 focused tests: UID0 for archived root-owned files, UID1000 for restored app files, and rejection of foreign UID.
- Signed v0.6.51 package deployed staging-only; production_modified=false, migration_allowed=false.
- The pending v0.6.50 restore journal was recovered via recover-online; checkpoint undo restored with matched SHA-256, PostgreSQL and Qui became healthy, and Qui responded HTTP 200. Recovery journal cleared.
- A real restore-online from previously verified v4 PostgreSQL cold checkpoint data-e235e63d9043 then succeeded; saved new undo data-6af6d5351b5a, verified PostgreSQL offline state and restored content, and restarted PostgreSQL followed by Qui with health checks.
- Qui's authenticated project-scoped gateway returned HTTP 200 after real restore; both app services healthy, second staging app MySpeed left untouched.
- Unneeded older transient test undo data-5bf1ab15ed08 was deleted explicitly, retaining the original baseline and latest restore undo. No production container or external Nextcloud HDD was modified.
- General cross-app database consistency and production-equivalent App Store parity remain unproven, and production cutover is blocked.
