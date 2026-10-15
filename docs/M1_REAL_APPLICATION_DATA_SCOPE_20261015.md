# M1 real application migration coverage — 2026-10-15

The Docker inventory and Compose UI are now LIVE on the local
OpenServerDesk staging API, **not production**.

This release adds a non-mutating application data preservation preflight:
`tools/migration/m1_app_data_inventory.py`. It queries the existing Docker
Engine for all containers, Compose project references and mounted sources.
It stores mount source paths, paths to Compose project files and recovery
coverage detail **only in a local root-private file** (0600) under
`/opt/openserverdesk-dev/runtime-stage/M1_PRIVATE_APP_DATA_INVENTORY.json`.

A separate redacted summary (no path, label, environment, credentials, or
per-container identifiers) is published to the local staging dashboard at
`/api/v1/migration/data-coverage`. The web UI displays how many sources
would require verified recovery and explains that migration is still blocked.
The data includes a timestamp; this is a snapshot, not a continuous monitor.

Verified on the actual 2026-10-15 Docker Engine:
- **16 containers**, all running
- **10 Compose projects** referenced
- **30 unique bind sources** used by those containers
- **0 referenced Docker named volumes** (not a claim that no other data exists)
- **25 running writable bind/volume mounts**
- **0 bind source paths flagged for operator review** under the narrow
  static-type checks (not an independent security or data consistency audit)

The inventory did NOT stop apps, lock database files, copy data or inspect
any production secrets or database contents. Thus there is **no proof of a
consistent full backup** or a safe activation/rollback of these real workloads.
Quiescence, destination storage sizing, external filesystem coverage, restore
and rollback still must be explicitly planned and validated before M1
cutover is permitted.

The local Docker inventory feature is explicitly enabled in staging by
a root-owned, non-world-writable opt-in marker at
`/opt/openserverdesk-dev/runtime-stage/.enable-docker-inventory` with the
exact text `OSD_STAGING_DOCKER_INVENTORY_V1`; it is not an API parameter and
cannot enable production writes. The API is bound to loopback. This still
does not make raw Docker socket access a low-privilege capability;
privilege-separated production design and authenticated access are required.

Latest package builder: `tools/staging/build-m1-functional-dashboard.py`
produces the inert staging-only `openserverdesk-m1-candidate_0.6.1_amd64.deb`.
The release decision remains explicitly fail-closed.
