# M1 staging runtime integration checkpoint — 2026-10-15

ReCasaOS Gateway binary was deployed **only inside a network-isolated Docker staging
container** using separate configuration, runtime files and storage. It answered
`GET /ping` with HTTP 200 and `pong from gateway service`. No host port exposed.

ReCasaOS UserService binary booted in a separate container sharing only the
staging Gateway's network namespace and runtime directory, with its own
`/var/lib/osd-user` database directory. Its internal listener started, but it
could not register its event types because there is **no Message Bus staging
service or `message-bus.url`**. This is a partial startup, not an end-to-end
authentication PASS. UserService staging was stopped to avoid repeated failed
registration/log spam.

Next minor: build and run ReCasaOS Message Bus with the same isolated runtime,
then verify UserService's event registration, gateway routes, and authentication
using **only synthetic staging users**. Do not connect to production CasaOS
runtime files, databases, sockets or Docker host network.

Production CasaOS services were confirmed active after this test.
No real upgrade/rollback or M1 pentest has passed yet.
