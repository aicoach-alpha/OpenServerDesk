# OpenServerDesk v0.6.25 — LIVE isolated multi-service Compose

Date: 16 October 2026, staging-only on andre-nas.

This release adds actual multi-service topology management:
- Two to four validated dependent services, with a strictly
  controlled offline BusyBox image, network none, no ports,
  no privilege escalation, no app-supplied commands, environment
  secrets or user-data bind paths.
- Structure-only topologies may be tested through the authenticated
  /api/v1/stage/topologies GET/POST API and the dashboard.
- Topology requires stage-only project prefix; every lifecycle
  operation verifies the actual immutable 64-character container
  IDs, Docker Compose labels, stage owner, read-only root filesystem,
  sandboxed bind path and network confinement.
- Supports install, list, stop, start, restart and uninstall of
  multiple services. Uninstall individually rechecks each remaining
  owned ID and leaves staging data for recovery; it never invokes
  Compose down on an unknown project.
- Actual direct 2-service Docker Compose lifecycle passed. Actual
  authenticated HTTP 3-service topology lifecycle passed, including
  staged reader role POST denied with 403 and unauthenticated GET
  denied with 401.
- The HTTP E2E verified all 16 preexisting Docker container IDs are
  unchanged at the end of the operation; temporary test identities
  were deleted from the stage-only identity store after the test.
- 70 unit tests passed from a clean Git source archive.
- Package version 0.6.25, SHA256:
  a12d80072d3d305930ad36c54793eaa673697ef67ab9470485866f354a06a006
- Clean package source SHA:
  073f6075e5fa00c2ce1ba2f2b2ba180c9e8f19b6
- Actual packaged staging process runs under:
  /opt/openserverdesk-dev/releases/0.6.25/usr/lib/openserverdesk/server/app.py
- The staging-only SHA-pinned upgrade controller includes
  a durable rollback journal to the v0.6.24 process.
  Postdeploy receipt is present and pending journal absent.
- Detached Ed25519 local STAGING signature independently verified.
  This does not count as independent production security acceptance.
- CasaOS production services all remain active. No user uploads
  or Nextcloud external HDD content was read, moved or copied.
  Existing production apps were not modified.
- User-disabled 15-minute cron monitoring remains OFF.

LIMITATION: Staging multi-service topology uses fixed offline, unprivileged
images and no published ports. It is NOT general imported real CasaOS
application feature parity. Cross-service consistent migration,
in-place production activation/rollback and independent security gate
remain blocked. Production migration_allowed=false. The milestone
acceptance metric remains 40%, not elapsed-time completion percent.
