# OpenServerDesk Alpha 0.7.0-alpha.32 — safe failed-install compensation

## Development
- Automatically compensate a failed isolated stage install after its
  durable install journal has been written.
- Before any destructive action, validate the exact stage manifest and
  container ownership/provenance once, and validate Docker Compose network
  identity plus every currently attached container ID. Unknown or foreign
  endpoints abort cleanup BEFORE removing anything.
- Remove only the immutable IDs verified to belong to that unique
  osd-compiled stage project, then verify/destroy its own network.
- Restore the registry and remove the pending journal if compensation
  fully succeeds. If verification/cleanup fails, RETAIN the journal and
  surface the existing manual recovery-required error.
- Preserve all stage data directories under the existing retention policy;
  no host or production data is deleted.
- The protected Qui staged PostgreSQL pilot keeps its preexisting
  delayed-readiness/finalization workflow; never automatically erase its
  instance on startup timeout.
- Journal unlink on a successfully committed install is outside startup
  compensation, avoiding accidental deletion of a healthy app.

## Targeted acceptance
- Four focused tests: failed stage install cleans exact container and
  registry; foreign network rejected before Docker removal; Qui keeps
  recovery journal; unverified containers cannot be deleted.
- All tests mock Docker and act only on ephemeral temp stage records.
- Integrity check after Alpha deployment: healthy public endpoint,
  unchanged registered original stage projects, and all six CasaOS
  production units active.

## Safety and scope
- No CasaOS production cutover, Docker host-wide cleanup, unrestricted
  socket exposure, migration, or access to external Nextcloud user HDD.
- Keep previously verified App Store staging capabilities unchanged.
