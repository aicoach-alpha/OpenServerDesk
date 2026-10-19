# OpenServerDesk 0.6.45 — dependency-aware multi-service lifecycle

- Staging app stop/restart and data checkpoint quiesce now halt dependents before prerequisites, following the validated reverse DAG.
- Start, restart and recovery resume prerequisite services before their dependents, preserving previously stopped state where possible.
- Multi-service Compose catalog depends_on dictionary conditions service_started and service_healthy are retained, rather than flattened. One-shot service_completed_successfully is rejected until job support exists.
- A service_healthy prerequisite must have a real Docker healthcheck reporting healthy before its dependent starts. Missing/unhealthy healthcheck fails closed; readiness does not claim healthy containers when Docker reports starting or unhealthy.
- Reject circular, self and unknown dependencies in runtime manifest.
- Docker read-only service inventory exposes health status, dependency names, and startup order in authenticated staging UI.
- Docker identity/volume guards remain in place: no production Docker mutation, no external Nextcloud user storage, no extra network privileges.
- Implements lifecycle semantics, NOT native install parity for all 107 multi-service CasaOS entries. Full multi-service install still needs cached images and app-specific environment/secrets support.
- Production cutover remains disallowed.
