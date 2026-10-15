# M1 v0.5.0 all-six upstream services isolated startup — 2026-10-15

The complete pinned v0.5.0 payload was unpacked, and a single isolated
Docker staging stack was launched with all six actual upstream executables:

- ReCasaOS Gateway (serving the packaged upstream UI)
- ReCasaOS MessageBus
- ReCasaOS UserService
- ReCasaOS Core
- ReCasaOS AppManagement
- ReCasaOS LocalStorage

The test at `tools/staging/verify-m1-full6-runtime.py` uses one isolated
Gateway namespace (`--network none`), five containers sharing **only that
test namespace**, ephemeral stage-owned configuration, data and runtime
directories, and no published host ports. Every process has read-only
root filesystem, dropped capabilities, bounded RAM/pids and no production
mounts, credentials or Docker daemon socket.

One targeted startup check confirmed all six service processes RUNNING,
packaged UI served from the staged Gateway, and UserService's fresh routed
`GET /v1/users/status` response. All disposable containers were removed.

Observed `FULL6_ISOLATED_PROCESS_BOOT_AND_USER_ROUTE_PASS`.

**Narrow interpretation:** full six-service *process startup* plus routed
UserService status PASS. This does NOT validate AppManagement Docker management
(which cannot access a Docker engine in the intentionally socketless stage),
LocalStorage host filesystem/mount functionality, GUI workflows, release
signing, full in-place application migration, or production rollback.
These remain M1 blockers. Do not unlock migration readiness.
