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
installer gate are implemented. A staging-only Debian candidate (v0.5.0)
now bundles pinned ReCasaOS Core, Gateway, UserService, MessageBus,
AppManagement, LocalStorage and upstream dashboard UI. Its file installation
and isolated Gateway serving the packaged UI have passed. This does **not**
mean that the six services are integrated, that the dashboard is fully
functional, or that production cutover, full recovery, security release
approval, Docker updater, GPU installer or OTA are available.

Do not run a migration on a live CasaOS installation with this prototype.

## Source layout
- `tools/migration/`: migration proof-of-concept scripts
- `tests/`: focused Python unit tests
- `docs/ROADMAP.md`: gated development roadmap

## License
Apache-2.0 for original code in this repository. When upstream sources are imported,
their individual licenses and attribution must be preserved. Not affiliated with IceWhale or ReCasaOS.
