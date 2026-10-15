# M1 functional local Docker inventory — 2026-10-15

**Usable staging feature, not a complete or production-safe M1 migration.**

OpenServerDesk's own functional dashboard is served at `/ui` by the
read-only Python staging API. Its frontend polls `/api/v1/docker/containers`
to display actual container count, running status, Compose project groups,
images and published ports. It has responsive styling and dynamic refresh,
not a static upstream screenshot or a mocked Docker dataset.

`server/docker_readonly.py` sends only a fixed Docker Engine GET request
to the local UNIX socket; it does not accept caller-supplied socket paths or
Docker API routes. Environment variables, raw labels, host bind paths,
container configuration and Docker logs are never returned. JSON-to-DOM
fields use textContent, not HTML injection.

**Integration proof:** using the real local Docker Engine, one isolated
staging API invocation returned 16 actual containers, grouped into 10
Compose projects. Its UI HTML/JavaScript were served; POST was rejected with
HTTP 405; read-only production-mutation capability stayed false.
`REAL_DOCKER_INVENTORY_AND_USABLE_UI_PASS`.

The service defaults to Docker inventory disabled, requiring
`OSD_DOCKER_READ_ONLY=1` as an explicit local staging opt-in.
The HTTP server refuses to bind a non-loopback host.

**Security limitation:** possession of Docker socket credentials is a
high-privilege capability in itself. Restricting this application's HTTP
handler to GET does not reduce the socket's underlying operating-system
privileges. Thus this is not a public-network feature; authentication,
privilege separation and a constrained external read-only Docker broker
are required before a production deployment. No production service or
container was changed to run this gate.

**Still outstanding for M1 FULL PASS:** integrated ReCasaOS application
management and local storage workflows, complete persisted application
migration and safe cutover/rollback, signed release and scoped independent
security acceptance.

**Packaged release candidate:** `openserverdesk-m1-candidate_0.6.0_amd64.deb`
ships the functional HTML/CSS/JavaScript and `docker_readonly.py` inside
the complete 6-component upstream staging package. An isolated dpkg root
was installed and the **installed** Python API process (running as user
`andre`) enumerated the same 16 actual Docker containers and 10 Compose
projects, served the installed UI, and rejected POST with HTTP 405.
`PACKAGED_REAL_DOCKER_UI_AND_COMPOSE_INTEGRATION_PASS`.
The candidate is a staging artifact, NOT a production-safe installer.
