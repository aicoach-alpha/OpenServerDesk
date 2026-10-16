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
installer gate are implemented. A staging-only Debian candidate (v0.6.10)
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

Platform configuration only: Nextcloud user uploads and external HDD
user data are excluded from migration backup selection. Docker data
mount locations remain unchanged. The previously suggested 1-2 TiB
extra HDD is NOT required by this CasaOS replacement scope. See
docs/M1_PLATFORM_SCOPE_CORRECTION_20261016.md.

Scoped CasaOS configuration now has an **actual SSD backup and independently
verified staging restore**, including three SQLite databases. No Nextcloud
user-upload contents were opened or copied. See
docs/M1_REAL_CONFIG_SSD_RECOVERY_20261016.md. The result is NOT an
atomic cross-service snapshot and does NOT authorize production cutover.

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

## Current real-migration limitation

The v0.6.6 candidate carries a read-only topology API for 30 actual Docker
bind sources spanning three filesystems. Two sources have multiple writable
consumers and require a coordinated quiescence plan. The staged checkpoint
controller does not cover these production mounts and is not a replacement
for an independent full host migration/rollback controller. No production
cutover is authorized or implemented; do not disable CasaOS.

The hourly ChatGPT automation and the 15-minute NAS cron monitor were
disabled at the owner's request on 2026-10-15. No continued automatic
engineering is implied by an existing staging service.

The v0.6.7 candidate adds gated cold Docker/Compose app-data backup and private isolated restore; see docs/M1_REAL_DATA_COLD_BACKUP_20261015.md.

The packaged staging API is now **actually running** from the v0.6.8
candidate under the OpenServerDesk-only systemd unit. It is independently
reversible to the previous staged package, and remains distinct from all six
production CasaOS services (see docs/M1_STAGING_PACKAGE_LIVE_UPGRADE_20261015.md).
This is still **not** a full in-place CasaOS replacement.

The v0.6.9 staging candidate adds exhaustive Docker/Compose cold-backup
integrity verification including ACL/xattr, hardlink graph, full-tree
membership and external symlink fail-closed checks. See
docs/M1_BACKUP_INTEGRITY_HARDENING_20261015.md. This does not authorize
production migration.

The v0.6.10 staging candidate packages the independent-device storage
safety gate. Both actual cold backup and recovered-data publication reject
destinations located on any filesystem containing the original Docker/Compose
sources. See docs/M1_REAL_STORAGE_BLOCKER_20261015.md. Production migration
remains blocked pending independent backup storage and further acceptance.
