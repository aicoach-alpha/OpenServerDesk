# OpenServerDesk Alpha 0.7.0-alpha.10 — App Store Capability & Lifecycle

## Delivered
- CasaOS local catalog: 726 applications, 100% classified with no host data copied.
- 667 isolated-stage sandbox **plans**, 53 host-integrated apps deliberately
  restricted, and 6 requiring Compose metadata/runtime adaptation.
- Added numeric-leading service names (2fauth), /mnt and /media destinations
  using FRESH stage-owned bind source directories, and exact duplicate
  mount declaration normalization. Conflicting duplicate destinations fail.
- Docker sockets, CasaOS/Docker engine storage, kernel trees and credential
  files remain blocked; no general privileged mode or production writes.
- Host-integration and metadata blocked apps have distinct filters and
  explicit requirements shown on the live App Store.
- Authenticated stage-only browser gateway accepts a SINGLE Docker-verified
  isolated project's compiled HTTP target. No caller-supplied URL/IP/port;
  private network, exact project registration, full container provenance,
  authorized write-operator session cookie, and strict origin checks.
- Existing explicit MySpeed outbound pilot remains exact-ID restricted.
  Protected Qui stays inspect-only. Any unauthenticated operator API
  request is denied.
- App cards show Open web app only for an eligible, running, stage-owned
  project. Container start/stop/restart/uninstall/update/rollback/backup
  continue using previously existing stage-only role-checked APIs.

## Acceptance & limits
- One focused source/inventory compatibility contract gate PASS (no new
  Docker-per-app tests). Previous isolated MySpeed lifecycle E2E remains PASS.
- Sandbox planning **does not mean functional runtime equivalence**:
  original environment, mounts, network settings, privileges and user data
  remain deliberately stripped, and many apps require those features.
- Browser gateway supports HTTP(S) UI proxy at the alpha HTTPS hostname;
  arbitrary third-party app login, cookies, WebSockets and app-specific
  asset paths have not been proven. Not a generic privileged reverse proxy.
- 53 host-integrated apps cannot be marked ready under existing production
  protection rules. 6 need one-shot service support or metadata fixes.
- Full CasaOS parity, data migration and production cutover are NOT PASS.
  Production CasaOS stays active; no Nextcloud user data is touched.
- Release origin: 192.168.31.31:18691; public https://osd.vervue.my.id/.
