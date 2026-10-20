# OpenServerDesk 0.7.0-alpha.36 — inspect empty staging folders without deletion

## Implemented
- Authenticated read-only GET /api/v1/stage/store-compiled?project=<id>
  now returns scoped empty-preparation eligibility and a stable refusal code
  without exposing file contents, secrets, host paths or production metadata.
- Stage-only read authorization is required for preview. Existing explicit
  POST clean-preparation continues to require write authorization.
- The cleanup validator is shared between preview and the actual mutation:
  project registration, 10-minute idle period, exact ownership, filesystem
  device, symlink and mount boundaries, generated metadata, empty volume
  directories, recovery journal and Docker project name collisions.
- The operator must click Inspect eligibility before Clean only if empty is
  enabled. On refresh, old approvals expire. The server re-runs the full
  validator under the staging lock during actual deletion, so previews cannot
  authorize stale data.
- Browser controls never access local host paths or render untrusted markup.
- No cleanup is executed as part of the deployment; all old 15 unregistered
  staging folders and the 2 registered baseline projects remain untouched.
- Six targeted read-only/cleanup contract tests PASS for empty, data-bearing,
  recent and registered projects. No blanket Docker testing.

## Boundaries
- Safe sandbox compilation is not full application runtime parity.
- CasaOS production remains authoritative; no production cutover.
- Nextcloud external HDD and all CasaOS user files remain unchanged.
