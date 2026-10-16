# OpenServerDesk v0.6.24 LIVE staging: CPU/RAM/process metrics

Date: 16 October 2026. Read-only staging release; NOT production CasaOS
replacement or a 100% feature parity claim.

Functionality shipped:
- server/docker_metrics.py executes exactly docker stats --all --no-stream
  with a fixed JSON format (no shell or untrusted command arguments).
- Every Docker stat ID must match the preexisting read-only Engine inventory.
  Unexpected/missing/duplicate IDs, failed CLI, malformed CPU/RAM/PID values,
  large responses and concurrent inventory races result in explicit
  HTTP503, not guessed resource values.
- Only CPU percent, used/limit memory bytes, memory percent, PID count and
  existing 12-char container ID are public. User file content, env variables,
  application logs, mount paths, secrets and Nextcloud uploads are NOT read.
- The dashboard now displays actual per-container CPU, RAM MiB and process
  count in the existing inventory table. If resource stats are temporarily
  unavailable, the inventory remains accessible and the UI reports the
  resource error rather than fabricating numbers.
- LIVE GET /api/v1/docker/resources returned HTTP200 and exactly 16
  sanitized container rows, matching 16 IDs from the inventory endpoint.
- v0.6.24 was built from a clean archived Git tree at
  a91dbfc724afa2dd44b399161408bf376895d521, to avoid including
  concurrent uncommitted development modules in the package.
- Version-specific controller tools/staging/upgrade-packaged-stage-0624.py
  pinned the prior 0.6.23 stage and exact v0.6.24 package hash,
  with durable journal and automatic 0.6.23 rollback on failed post-deploy
  checks. The live unit runs the packaged 0.6.24 app under
  /opt/openserverdesk-dev/releases/0.6.24/.
- Candidate SHA256:
  8dc4c94a5522c0115b8e64863f4abad5c23c6d513b5b5b437a48dd2d74ebb52f.
- Detached staging Ed25519 manifest and signature verified against the
  locally held PUBLIC staging key: OpenServerDesk-stage-0.6.24.manifest.json
  and .manifest.sig, under /opt/openserverdesk-dev/build/. This is a
  local STAGING signing identity, NOT independent production signing.
- The six original CasaOS production services stayed active. No production
  app lifecycle operations were executed. User-disabled automatic progress
  monitoring remains OFF. migration_allowed=false.
- The accepted release-scope percentage remains 40/100. General app parity,
  consistent multi-service migration, reversible production cutover, and
  independent security acceptance remain outstanding.
