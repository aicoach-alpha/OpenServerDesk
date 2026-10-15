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

## Physical staging results — 2026-10-15
- Offline Message Bus `go test ./...` and binary build PASS.
- Dedicated staging config and persistent storage were required; default DBPath
  points at `/var/lib/casaos` and was blocked by read-only root. Corrected to
  an isolated `/var/lib/osd-bus` bind mount; no production mount was used.
- Gateway and Message Bus staging RUNNING, Message Bus HTTP listener and
  message-bus.url created.
- UserService startup RUNNING, but websocket subscription to
  `/v2/message_bus/event/local-storage` failed HTTP 400 on a fresh bus.
  Upstream SubscribeEventWS returns 400 when no source event types are
  registered; no LocalStorage staging producer exists yet. UserService stopped
  to avoid repeated failed retries.
- Authentication and complete event integration NOT PASS. Do not manufacture
  an event registration or weaken bus authentication to bypass this check.
- Production CasaOS services remained active.
