# M1 isolated authentication staging gate — 2026-10-15

Three ReCasaOS staging containers were running in a separate Docker network
namespace, using synthetic UserService database and runtime paths.

The actual staged Gateway returned HTTP 200 for `GET /v1/users/status`,
and reported an initially uninitialized staging user database.

A one-shot Python test generated a random staging-only username and password,
obtained the temporary registration key, registered the synthetic account via
`POST /v1/users/register`, and authenticated the same account via
`POST /v1/users/login`. Both responses returned HTTP 200 and a JSON application
success code of 200. No usernames, passwords, keys, or tokens were printed.

**Verified PASS:** first-time synthetic registration and password login over
the staging Gateway, backed by the isolated UserService database.

**Not yet verified:** access-token use against protected routes, refresh token
rotation, real CasaOS account migration, full rollback, or the security gate.
Do not mark M1 complete on the basis of this test.
