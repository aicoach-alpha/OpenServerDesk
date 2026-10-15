# M1 authenticated real staging application manager — 2026-10-15

**Functional on the NAS OpenServerDesk staging service only. NOT production.**

The dashboard offers an authenticated Docker app lifecycle and stage-only
local file operations. It uses a 256-bit bearer token held in the private
0600 local path /opt/openserverdesk-dev/runtime-stage/stage-app-manager/token.
The user can supply the token to the password field in the loopback UI; the
UI never persists the token in browser storage. No credentials appear in
GitHub, documentation or application logs. HTTP Host and Origin require
localhost/127.0.0.1, bound service port. No CORS sharing.

## Real lifecycle

* GET /api/v1/stage/apps: only owned registered stage apps.
* POST /api/v1/stage/apps with action=install: new bounded BusyBox instance
  with --pull never, --network none, --read-only, --cap-drop ALL,
  --security-opt no-new-privileges, --memory 64m, --pids-limit 32,
  --restart no, no ports and no host mounts.
* POST action=start, stop, restart or uninstall: exact full ID in private
  stage registry. Every mutation double checks Docker immutable owner labels,
  exact ID, image, name, network mode, no port binding, no privileged mode,
  and no host mounts. Existing production app IDs cannot be mutated.
* GET /api/v1/stage/files and GET with ?name=...: list/read stage-only
  UTF-8 files under a confined directory file descriptor.
* POST /api/v1/stage/files with action=create/delete: create or delete a
  single flat named file, max 64 KiB per file; O_NOFOLLOW and hardlink and
  symlink guards, no path traversal or implicit overwrite.

The service keeps ProtectSystem=strict, NoNewPrivileges=yes, PrivateDevices,
empty capability bound. The service-scoped drop-in opens only
ReadWritePaths=/opt/openserverdesk-dev/runtime-stage/stage-app-manager.
Raw Docker socket credentials remain high privilege and are NOT appropriate
for public production; privilege separation remains mandatory.

## Authentic live staged UAT

LIVE_AUTHENTICATED_STAGE_APP_DOCKER_INSTALL_STOP_START_RESTART_REMOVE_PASS
ALL_EXISTING_DOCKER_CONTAINER_IDS_PRESERVED_PASS (16 existing containers)
UNAUTHORIZED_FORGED_ORIGIN_AND_PRODUCTION_ID_REJECTED_PASS
LIVE_AUTHENTICATED_ISOLATED_LOCAL_STORAGE_CREATE_READ_LIST_DELETE_PASS
TRAVERSAL_WRONG_TOKEN_AND_OVERWRITE_REJECTED_PASS

No arbitrary image install, full upstream ReCasaOS AppManagement/LocalStorage
integration, public multi-user SSO, production Docker management, full
application migration/rollback, or independent security signoff has passed.
Migration remains forbidden. The stage mutator is NOT automatically enabled
on new installs of the inert candidate Debian package.

The user requested the M1 automatic tasks disabled; the previous progress
bar may show a historical 32% score but does not represent live work.
