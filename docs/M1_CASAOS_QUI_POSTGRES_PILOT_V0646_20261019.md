# OpenServerDesk v0.6.46 — exact Qui + PostgreSQL App Store pilot

The native CasaOS catalog entry casaos.app:org.icewhale.qui names Qui 1.28.0 and PostgreSQL 16 Alpine, with a service_healthy dependency and application-specific environment requirements.

- Pulls exactly the two existing local-catalog image tags into Docker's image cache, then pins immutable sha256 image IDs. This does not run or modify CasaOS containers.
- Only this exact catalog ID with exact service names/image tags/declared DB environment can receive two generated stage-only environment dictionaries.
- Generates one random 48-hex database password per generated project, stored as root-owned mode 0600 JSON on the internal staging filesystem. Uses the same password for Postgres and Qui's private Docker-network DSN. The production CasaOS passwords and databases are never read.
- The Postgres container has a bounded pg_isready healthcheck; the Qui service depends_on postgres with condition service_healthy. Both remain nonprivileged UID1000, with all Docker capabilities dropped, no new host-network access, and stage volume paths only.
- Only Qui's HTTP 7476 target is mapped to a server loopback stage port. Remote browser access for Qui is not exposed; the v0.6.41 browser gateway remains MySpeed-only.
- The runtime denies unknown environment keys, changed password, changed healthcheck, incorrect app IDs, and missing immutable Docker provenance.
- Functional staging UAT must still establish actual boot, DB connectivity, and HTTP availability; image presence or passing unit tests alone does not count as successful installation. Prod cutover remains prohibited.

## Authentic runtime UAT evidence
- Native CasaOS Qui 1.28.0 and PostgreSQL 16-alpine immutable images were pulled from their catalogue-declared references (approximate Docker image sizes 107 MB and 419 MB).
- Genuine compiled staging install created a dedicated internal Docker bridge and stage-only database password. Both services started and Docker healthchecks reached healthy. PostgreSQL logged ready to accept connections and Qui logged successful PostgreSQL initialization.
- Initial install was held in a durable pending journal because Docker internal bridge loopback host port publication was not reachable; this is corrected in v0.6.47 without granting app egress.
- This was an authentic staging failure in v0.6.46, not an install PASS at that point.
