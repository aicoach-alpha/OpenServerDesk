# M1 isolated Message Bus integration gate

Upstream: ReCasaOS/CasaOS-MessageBus, pinned commit
5249d6443ae55bc6d4e9ccb5f88a49ffddabee1e.

Build procedure: run go mod download/go generate in an isolated writable
workspace, then run go test and go build without network, with limited
resources and read-only source.

Deployment must use only the dedicated `osd-m1-gateway` container's Docker
network namespace. Never use Docker host networking or production CasaOS
runtime folders, `/etc/casaos`, users, or databases.

Success criteria:
- Message Bus service starts and registers a route at the staging Gateway
- UserService staging starts with a fresh synthetic database and registers its events
- Gateway and UserService health and route tests PASS
- Production CasaOS services remain active and unaffected

No user migration/rollback or pentest PASS is inferred from this runtime gate.
