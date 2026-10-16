# OpenServerDesk v0.6.32: native App Store multi-service safe staging compiler

16 October 2026 — staged implementation on andre-nas.

Feature batch:
- Compiler accepts 1 to 6 catalog services, checks service dependency
  DAG and rejects missing/duplicate/cyclic references.
- For a Compose image referenced by an explicitly versioned, unversioned,
  or 'latest' tag, a read-only Docker image inspect resolves a locally
  cached immutable sha256 content ID. The staging launch code in
  stage_store_general uses the immutable content ID, not a mutable tag.
  No implicit image pull, host port/network reuse, or original Compose
  execution occurs in the compiler.
- Generated stage-only Compose plan sets network_mode none, no published
  host ports, drops ALL capabilities, disables privilege escalation,
  sets a numeric unprivileged UID, memory/PID limits, local cached
  immutable images and safe dedicated staging volume sources. Original
  bind source paths, environment values and commands are NEVER copied
  into that plan. This is not yet a running general multi-service app.
- Authenticated GET /api/v1/stage/store-compile?id=... returns only a
  sanitized preview: service count, service order, volume count, and
  available cached image count. The dashboard shows this preview in
  CasaOS App Store details.

Measured classification on the local cached CasaOS store:
- 726 definitions examined.
- 20 multi-service definitions met the current structural compiler
  constraints (without guaranteeing cached images, successful installs,
  or application functionality). Others need additional Compose/volume
  and image handling.

Post-deploy HTTP staging UAT with a temporary read-only stage identity:
- default:MySpeed: 1 service, 1 cached image, PASS preview.
- casaos.app:org.icewhale.blinko: 2 services, 0 cached, PASS preview.
- casaos.app:org.icewhale.docmost: 3 services, 0 cached, PASS preview.
- Missing authorization returned HTTP401.
- The 16 preexisting Docker container IDs were exactly unchanged.
- All temporary stage identities from UAT were removed.

10 focused compiler/immutable image tests PASS.
Package 0.6.32 SHA256:
8bfa8cbd4495b185976dbae815d3f8087dd573ed947a4ede6962122ecf5ebe3d
Clean source Git SHA:
dfd0570c2303c3c419cb2bcdab72c073127537c7
Local staging Ed25519 manifest/signature verified. Journaled controller
upgraded only OpenServerDesk staging from 0.6.31 to 0.6.32 with
staging-only rollback if verification fails. No production CasaOS unit
was replaced or stopped. Nextcloud external HDD user files were not
opened, migrated or copied.

NOT COMPLETED:
- General multi-service install/start/update via Docker is NOT yet
  operational just because the compiler can create a plan.
- Safe stage-to-stage application updates and per-app rollback remain
  unfinished.
- Application networking, persistent original app data, public UI/port
  mapping, externally pulled untrusted images and complete App Store
  compatibility remain outside these acceptance proofs.
- M1 weighted production release acceptance remains 49% on last valid
  snapshot, migration_allowed=false. The user-disabled automatic status
  cron was NOT re-enabled.
