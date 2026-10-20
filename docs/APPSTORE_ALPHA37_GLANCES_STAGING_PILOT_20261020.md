# OpenServerDesk Alpha 0.7.0-alpha.37 — Curated Glances read-only staging pilot

## Implemented
- New exact-match Glances CasaOS catalogue adapter ONLY for
  github.com:com.bigbeartechworld.glances and the digest-pinned
  nicolargo/glances:4.5.3.2-full image. App ID, service, image, source
  environment, web port, socket mount and source host-PID flag are
  explicitly verified; changed digest, privileges, devices and arbitrary
  extra volumes fail closed.
- The original real Docker socket is NEVER mounted. Glances receives
  ONLY the existing synthetic staging-owned read-only Docker metadata API.
- Source host PID namespace is intentionally discarded, and the runtime
  rejects any stage manifest with a PID namespace declaration or a container
  that unexpectedly uses a host PID namespace.
- Only GLANCES_OPT=-w is intentionally retained to enable the stage
  web interface. Original host timezone/env and process access discarded.
- The app's HTTP endpoint is reachable only via the existing authenticated
  project-specific stage web gateway on an internal-only Docker network.
- New stage-only Glances startup budget of up to 35 seconds for initial
  Python web runtime. General stage resource limits remain intact.
- Five focused tests verify the pinned compiler, container identity/UID,
  no PID inheritance, rejection of changed host privileges and exact
  stage-only catalogue metadata.
- 675/726 static sandbox plans now supported; 51 remain host-limited.
  Static planning coverage is NOT full app runtime functional equivalence.

## Boundaries
- Glances inside staging may monitor its own container and the sanitized
  stage Docker API, NOT the host's real processes, production metrics,
  CasaOS user applications or external Nextcloud HDD.
- The Docker facade exposes only limited read operations and bounded
  logs/events/stats. The Glances web UI needs one genuine staging UAT
  before runtime compatibility can be claimed.
- No production CasaOS cutover, no unrestricted host Docker API, and
  no user-data migration or external HDD access.
