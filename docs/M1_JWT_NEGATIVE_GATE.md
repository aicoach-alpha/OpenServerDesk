# M1 JWT negative gate — 2026-10-15

Runtime: three isolated osd-m1 staging containers confirmed running.

Observed through the staging Gateway at 127.0.0.1:18701:
- GET /v1/users/current with no authorization: HTTP 401.
- POST /v1/users/refresh with no refresh token: HTTP 401.

PASS only for denial of missing credentials. This does not prove
authenticated route access, correct JWT signature/expiry validation, refresh
rotation, or user-data migration. An earlier independent staging test proved
synthetic registration and password login (docs/M1_AUTH_STAGING.md).
Fresh synthetic login credentials were intentionally not persisted.

Next: repeat synthetic creation on a disposable fresh staging database,
retain credentials only within the testing process, and verify authenticated
/current plus valid refresh in the same execution. Do not access production
CasaOS users or authentication database.
