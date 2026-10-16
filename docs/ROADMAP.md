# Release gates
Major -> minor: implement, focused test, deploy DEV, post-deploy verify; upon full major deployment, integration verification, security assessment and scoped pentest, then PASS or fix.

## M1 Foundation (in progress; final acceptance BLOCKED 2026-10-15)

The reproducible final release decision and exact blockers are in
`docs/M1_FINAL_ACCEPTANCE_20261015.md`. Existing staging PASS results do
not imply full M1 release. Keep `migration_allowed=false`.
- M1.1 GitHub public repository: created; initial publish pending commit
- M1.2 CasaOS v0.4.15 read-only compatibility inventory: PASS dev
- M1.3 CasaOS settings/SQLite backup and restore rehearsal: PASS dev (not full application restore)
- M1.4 Debian prototype install/upgrade/downgrade: PASS staging, production updater not implemented
- M1.5 Complete upstream component **payload** in inert staging .deb: PASS (v0.5.0, pinned hashes, isolated Gateway served UI)
- M1.5 All six pinned upstream service processes + UI booted in socketless isolated staging: PASS (limited)
- M1.5 Two staged real Docker projects: quiescence gate, consistent SQLite/Compose/bind backup and independent restored tree startup PASS (not production-equivalent)
- M1.5 Packaged staging-only v0.6.8 activation and journaled rollback: LIVE staging PASS; not production cutover
- M1.5 REAL on-host platform-only SSD backup and staging-only restore verified: 1652 files, 3 SQLite databases; Nextcloud uploads and external HDD content excluded (PASS scoped, not atomic cross-service)
- M1.5 Full product integration, safe in-place cutover, rollback and final security gate: PENDING

- M1.5 Real staged Docker Compose catalog lifecycle and app-scoped durable
  backup/rollback v0.6.18: LIVE staging PASS; both approved app templates,
  authenticated API and UI, no network/ports, owner and bind checks. Limited
  catalog is NOT production CasaOS app parity
- M1.5 Real original CasaOS Compose compatibility baseline v0.6.19:
  18 valid definitions, 19 services, 45 port and 21 mount declarations;
  0/18 actual general imported apps E2E; Live staging read-only parity
  dashboard and release blocker ACTIVE (not full product parity).
- M1.5 Existing CasaOS Docker lifecycle/write parity, security and production
  readiness: still PENDING and must NOT touch user apps until approved

## M2 Docker core
Discovery, CLI/Compose stacks, ports and logbook.

## M3 Docker lifecycle
Explicit auto/manual/pinned per-app update policy, backup, verification and recovery.

## M4 GPU runtime
Hardware support matrix, host driver compatibility, NVIDIA/AMD/Intel container runtimes.

## M5 OTA
Signed updates, staged activation, rollback and recovery.

## M6-M8
Host management, user security and public release.
