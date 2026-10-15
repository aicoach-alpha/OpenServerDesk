# OpenServerDesk

An independent, community-oriented open-source project for an Ubuntu Server dashboard.
**Status: early development prototype — not ready to replace CasaOS.**

## Product direction
- Ubuntu Server 24.04 LTS stays as the host; no OS replacement
- Research ReCasaOS as the technical upstream; use ZimaOS as product/UX inspiration
- **In-place CasaOS migration** with configuration preservation, rollback and compatibility checks
- Universal Docker and Compose management, including stacks installed from the CLI
- Per-container auto-update policies (manual default, auto opt-in, pinned)
- Port inventory, allocation and historical logbook
- GPU integration for supported NVIDIA/AMD/Intel hardware
- Signed OTA updates, app backup and verified restoration

## Present status
The read-only migration preflight, backup/restore rehearsals and fail-closed
installer gate are implemented. A staging-only Debian candidate (v0.6.4)
now bundles pinned ReCasaOS Core, Gateway, UserService, MessageBus,
AppManagement, LocalStorage and upstream dashboard UI. Its file installation and isolated Gateway serving the packaged upstream UI
have passed. A separate OpenServerDesk-owned, functional read-only Docker
container/Compose dashboard is available at `/ui` when explicitly enabled
in local staging (see `docs/M1_REAL_DOCKER_INVENTORY_20261015.md`).
This does **not** mean the six services are fully integrated or the
production cutover, full recovery, security release approval, Docker
updater, GPU installer or OTA are available. An isolated, multi-project
app-data/Compose backup and restore tool is packaged for **staging-only**
rehearsals, with real Docker quiescence checks but no production cutover.

Read-only M1 acceptance progress is visible in staging /ui with 9 weighted
proof gates and 15-minute host-side status history (see
docs/M1_PROGRESS_MONITOR_20261015.md). The score tracks accepted milestone
scope, not remaining time; it does NOT automatically increase every interval.

Do not run a migration on a live CasaOS installation with this prototype.

## Source layout
- `tools/migration/`: migration proof-of-concept scripts
- `tests/`: focused Python unit tests
- `docs/ROADMAP.md`: gated development roadmap

## License
Apache-2.0 for original code in this repository. When upstream sources are imported,
their individual licenses and attribution must be preserved. Not affiliated with IceWhale or ReCasaOS.

## Authenticated local staging application management

An owner-labelled, isolated Docker application manager and a private file store
are functional on the loopback staging service. They require a local stage
operator token and cannot mutate existing production CasaOS containers.
See docs/M1_STAGE_APPLICATION_MANAGEMENT_20261015.md for scope and evidence.

By user request, both the OpenServerDesk hourly ChatGPT automation and the
NAS 15-minute cron monitor were disabled; any previous progress display
is historical until a fresh operator-initiated check is made.
