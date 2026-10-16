# OpenServerDesk v0.6.22 LIVE isolated staging multi-user authorization

Implemented on 16 October 2026 in staging ONLY: separate administrator,
operator and reader identities, without changing CasaOS production users,
the production Docker app state or Nextcloud external user upload files.

server/stage_users.py stores per-user random credentials as salted
PBKDF2-SHA256 hashes (300000 rounds), using strict owner-only 0700
directories and 0600 hashed identity records. Administrator can
read/write/admin; operator read/write; reader read only. The last active
administrator cannot be revoked and invalid bearer tokens fail closed.

The staging HTTP runtime never writes to the credential database. It
uses a shared read-only advisory lock, preserving the strict systemd
ProtectSystem confinement. Only authorized offline staging operators
can provision actors and revoke accounts.

The stage-only root-controlled marker enables multi-user authorization.
The pre-existing legitimate staging operator token was registered as a
hashed administrator credential, maintaining continuity of local stage
access. When activated, all stage GET and POST endpoints enforce scoped
read/write permissions. GET /api/v1/stage/whoami exposes actor, role and
allowed scopes but not credentials or hashes. The dashboard disables
writer controls for reader identities; server-side role enforcement is
authoritative.

LIVE staged v0.6.22 evidence: all three identities authenticated with
correct roles; reader POST returned 403; operator harmless invalid
POST was authenticated before returning validation error 400; invalid
token was denied 401. Unit and local HTTP regression tests passed.

Scope limitation: this is staging multiuser RBAC, NOT a production login
platform or full CasaOS parity. User onboarding, external identity
integration, account recovery and independent security audit remain
open. No CasaOS production service was stopped. migration_allowed=false
and weighted end-to-end milestone score stays 40%.
