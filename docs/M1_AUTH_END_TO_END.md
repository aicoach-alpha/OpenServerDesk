# M1 isolated authentication end-to-end UAT — 2026-10-15

A temporary UserService staging container was started with a **fresh synthetic
database** at `/opt/openserverdesk-dev/runtime-stage/uat-fresh-20261015/user-db`.
The existing staging UserService was stopped temporarily; neither production
CasaOS database nor Docker host networking was attached.

Executed `tools/staging/verify-auth-flow.py` against the isolated Gateway.
Actual output:

- ISOLATED_NETWORK PASS
- FRESH_DB PASS
- REGISTER PASS
- LOGIN PASS
- TOKENS_PRESENT PASS
- PROTECTED_ROUTE PASS
- REFRESH PASS
- AUTH_FLOW_END_TO_END_PASS

**Scope:** valid JWT-protected user profile access and valid refresh-token
exchange using a new synthetic user. Token rotation/replay invalidation,
expired/malformed token coverage, real CasaOS user migration and rollback,
and penetration tests remain unverified.

After the UAT the temporary UserService container was stopped and removed,
the previous staging UserService container restarted, and the previously
initialized staging user database status rechecked: PASS. CasaOS, CasaOS
Gateway, UserService, MessageBus, Docker and OpenServerDesk staging were all
active after restoration.

No credentials or token strings were committed or printed.
