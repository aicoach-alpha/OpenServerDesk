# LIVE v0.6.16 staging: CasaOS platform-only cutover readiness

New staging functionality shipped 16 October 2026:
A source-controlled, versioned cutover planning process evaluates real
metadata through Docker Engine and six CasaOS systemd services. It
independently re-verifies the root-private SSD configuration backup,
the separate restored configuration tree and all SQLite integrity checks.
It preserves Nextcloud user data bind mount references as opaque names,
never opens, traverses, hashes, copies or changes the external HDD.

The private output contains selected platform paths and the backup ID:
M1_CUTOVER_PLAN_PRIVATE.json (root-only mode 0600). Public sanitized
M1_CUTOVER_PLAN_PUBLIC.json is schema-validated by a read-only API:
GET /api/v1/migration/cutover-plan. Dashboard renders all nine conditions.

Five verified current conditions: scoped platform configuration only,
distinct SSD destination, matching platform source set, verified independent
backup+restore, and six running CasaOS original systemd services.

Four BLOCKED current conditions: cross-service atomic consistency,
complete production switch and recovery, independent production security
and signed release acceptance, and explicit maintenance authorization.
The endpoint always returns migration_allowed=false. No user uploads
were copied or opened, no production services stopped or changed.

Stage v0.6.16 installed through version-pinned, SHA-verified package
controller with a durable pending journal, automatic return to v0.6.15
on any failed health check. Real v0.6.16 health/UI/cutover/progress
API HTTP200; stage app API uncredentialed HTTP401. Production six units
stay active.

Package SHA256:
0910d8e2c9e65673fd5e57059eb2687a27dedf6448448764fa7c5d9426a355a4

User-disabled automated jobs remain disabled. M1 acceptance percentage
stays 40% weighted verified scope; this does not mean 60% time remaining.
This is a staging release, NOT a production cutover or FULL PASS.
