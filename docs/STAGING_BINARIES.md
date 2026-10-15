# ReCasaOS binaries: M1 staged verification
2026-10-15: Gateway and UserService upstream unit test runs passed.
Statically linked x86-64 binaries were built offline in a container and then
executed with --help inside separate network-disabled, read-only, capability-free
containers. This only validates startup argument parsing, not runtime readiness,
authentication, API integration, database migration or rollback.

Build output location: /opt/openserverdesk-dev/bin (not part of this repo).
No binary is deployed over CasaOS production. Runtime integration is BLOCKED
pending isolated configurations, correctly pinned service dependencies, and
a tested rollback path. See the SHA-256 records below.

CasaOS-Gateway ISOLATED_CLI_PASS
146368f9e2020dc997d0e676baba446fa8fff7a43449426b338b56a94107ebac  /opt/openserverdesk-dev/bin/CasaOS-Gateway
CasaOS-UserService ISOLATED_CLI_PASS
c3e8ddfda44c696f56c8577b09a5c50fc30022c4a29679d57c9902a75c16aafa  /opt/openserverdesk-dev/bin/CasaOS-UserService
