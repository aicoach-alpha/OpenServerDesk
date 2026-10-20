# OpenServerDesk Alpha 0.7.0-alpha.16 — capability broker foundation

## Deployed functionality
- Host Integration Broker v1: authenticated READ-ONLY stage metadata endpoint
  GET /api/v1/stage/host-broker with optional catalog app ID.
- It categorizes 54 apps needing host Docker/CasaOS API, devices/kernel,
  system services, protected system files, or DNS/network.
- For apps requesting Docker/CasaOS API, the OSD operator receives only
  verified stage-owned container health summaries using existing provenance.
- No raw Docker socket, arbitrary Docker API URL, host path, mount data,
  secrets, elevated privileges, or writable host lifecycle operations.
- The App Store UI can inspect an app's broker contract and unavailable
  host capabilities, but this inspection does not grant them to the app.
- All 54 privileged integrations remain DENIED at the container boundary.
- No external Nextcloud HDD, CasaOS production mutation, or cutover.

## Preflight version changes before stage downtime
- Version switch and catalog-driven Update compare immutable cached old/new
  image contracts before stopping containers or writing checkpoints.
- Compared Config fields: User, Entrypoint, Cmd, WorkingDir, Volumes,
  ExposedPorts. No image environment values or filesystem contents disclosed.
- MySpeed 1.0.8 declares User=node while latest declares User=empty.
  The new guard rejects this known incompatible cached image safely.
- UI distinguishes preflight refusal from a failed upgrade restored with
  its original staging data.

## Acceptance boundaries
- Four focused broker tests and four version-contract tests passed.
- 672/726 catalog entries have safe static sandbox plans, NOT confirmed
  equivalent runtime apps. 54 host-integrated apps still need individual,
  reviewed capability-specific runtime adapters.
- Stage core install, stop/start/restart and online backup/restore previously
  passed. An attempted MySpeed latest upgrade failed startup; automatic
  compensation restored its old image/data and removed the test fixture.
- This release adds early rejection of such incompatible upgrades.
- Existing CasaOS production, Nextcloud user data and external HDD remain
  completely outside staging. Production cutover NOT authorized.

## Alpha runtime
- User andre (UID 1000), user-level systemd.
- https://osd.vervue.my.id, origin 192.168.31.31:18691.
