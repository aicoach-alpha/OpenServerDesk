# Release gates
Major -> minor: implement, focused test, deploy DEV, post-deploy verify; upon full major deployment, integration verification, security assessment and scoped pentest, then PASS or fix.

## M1 Foundation (in progress)
- M1.1 GitHub public repository: created; initial publish pending commit
- M1.2 CasaOS v0.4.15 read-only compatibility inventory: PASS dev
- M1.3 CasaOS settings/SQLite backup and restore rehearsal: PASS dev (not full application restore)
- M1.4 Debian prototype install/upgrade/downgrade: PASS staging, production updater not implemented
- M1.5 Full runnable product, safe in-place upgrade, regression, rollback, security gate: PENDING

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
