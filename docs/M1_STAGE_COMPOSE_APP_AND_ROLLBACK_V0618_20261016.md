# v0.6.18 LIVE staging: real Compose application manager + rollback

**Release status:** functional staging LIVE. NOT production-parity signoff.

This release adds actual Docker Compose lifecycle from two fixed local-image
templates: an offline BusyBox HTTP website and offline BusyBox worker.
Authenticated API plus dashboard allows install, start, stop, restart,
uninstall, catalog browsing, scoped backup, restore, and interrupted restore
undo. Staging app data persists independently of the container; uninstall
never deletes its data. Runtime protection: no network, no ports, no privileged
containers, no host Docker socket, fixed image/user/resources, private stage
binds only. Every mutable Docker action revalidates stage-owner identity,
the exact full container ID, Compose project identity, the exact mount source,
and safety restrictions. Existing CasaOS apps are never eligible targets.

URLs (all stage-only authentication required):
- GET /api/v1/stage/catalog
- GET/POST /api/v1/stage/compose
- GET/POST /api/v1/stage/compose-backups

Independent Compose backups:
- stage_compose_recovery.py validates the exact Compose project set and
  image/owner/container identities and takes per-file SHA256 snapshots;
- restore has a durable pending undo snapshot before any changes, stops and
  resumes only checked stage-owned containers, and verifies restored hashes;
- recover restores pre-restore stage state from a pending undo snapshot;
- existing legacy stage-only file checkpoint now FAILS CLOSED if any
  Compose projects are registered rather than claiming incomplete backups
  were complete;
- stage-only Compose project data can never point to the external user HDD.

Real tests passed directly on Docker Engine:
1) actual Compose template install and HTTP server reading staged index.html;
2) worker service reads its persisted stage-mounted file through stop/start/
   restart; write via read-only bind fails;
3) authenticated HTTP catalog/lifecycle API, forged Origin and unknown
   CasaOS app operations are rejected;
4) real authenticated Compose checkpoint, deliberately corrupt a stage-only
   data file, restore, validate content and owner, verify legacy partial
   checkpoint rejected;
5) existing stage AppManagement+LocalStorage and its own checkpoint/restore
   functionality retested successfully;
6) all 16 existing Docker container IDs remain unchanged, all six CasaOS
   production services remain active.

Limitations: Only two allowlisted local offline templates so far, NOT the
full app catalog or general Compose import capability. No production app
lifecycle, data-volume migration, OTA, multi-user auth, host storage manager
parity or independent security clearance are asserted. Staging package
was activated using the SHA-pinned 0.6.17 to 0.6.18 journaled upgrade with
automatic staging rollback on health failure. Backup/restore remain stage-only.

SHA256 v0.6.18 staging package:
178a772cca7da6cd25d91e357b51ba15dc47e51947973772cd8ec68ef527aaea

User-disabled automated progress jobs remain disabled. The M1 full release
progress cannot be increased from this partial parity feature alone.
