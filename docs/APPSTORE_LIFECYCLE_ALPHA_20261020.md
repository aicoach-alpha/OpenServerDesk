# OpenServerDesk 0.7.0-alpha.6 — App Store & staged lifecycle

## Shipped implementation
- 726 CasaOS metadata records exposed through a **sanitized read-only** App
  Store endpoint; catalogue can be browsed before stage authentication.
- Local compatibility matrix shows 576 statically constructible stage-only
  Compose plans and 150 records requiring additional source support.
  All results are on-demand metadata analysis; NO broad Docker UAT.
- Supports exact `repository:tag@sha256:<digest>` references in source
  validation, image-cache preparation and immutable image-ID compilation.
- App Store search, filters, readiness details, and a direct
  prepare-image / install-stage action area are integrated into the Alpha UI.
- Isolated project count ceiling increased from 2 to 6; current occupants
  remain unchanged. Actual running containers remain stage-owned only.
- Application cards display start, stop, restart, uninstall when the operator
  possesses an existing stage write capability and the project allows writes.
  Qui with protected secrets remains inspect-only. Compiled store continues
  supporting update/rollback/checkpoint/recovery via its advanced controls.
- No host Docker/CasaOS production lifecycle mutations are enabled.
- Source ports, original mounts, network permissions and environment settings
  are not imported into stage deployments. Some apps may need further
  compatibility work before they function in the sandbox.

## Acceptance meaning (must not confuse)
- Compiled **sandbox planning coverage**: 576/726 (metadata only)
- Full functional CasaOS production parity: NOT PROVEN
- Installed-app production migration: NOT PERMITTED
- Imported original app data/Nextcloud files: NONE
- General runtime E2E verification for the 726 apps: NOT PERFORMED
- Existing M1 weighted 49% cutover milestone is intentionally unchanged.

## Live
- Public Alpha via Cloudflare Tunnel: https://osd.vervue.my.id/
- Origin: 192.168.31.31:18691
- Parallel staging 127.0.0.1:18690 and six CasaOS services remain online
- New user-facing App Store catalog browsing does not grant mutation access.

## UAT and operator clarity

One public browser test validated all 726 catalog records, 576 supported
static sandbox plans, compatibility filtering and read-only host inventory.
Without an authorized staging token the prepare/install buttons must remain
disabled and explicitly say login required. A dedicated Connect staging control
navigates to the existing token input; role-based API authorization is still
strictly enforced on every mutating lifecycle request.
