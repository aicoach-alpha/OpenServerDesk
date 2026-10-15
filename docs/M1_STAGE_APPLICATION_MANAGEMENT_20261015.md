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

## Staged real Docker application + LocalStorage integration

The staged BusyBox process is now UID 1000:1000 and sees ONLY
/opt/openserverdesk-dev/runtime-stage/stage-app-manager/files as a
read-only bind at /stage/files, rather than a broad parent mount or raw
production Docker volumes. Immutable owner/namespace/source/readonly/UID
conditions are checked again before every container lifecycle mutation.

A true live HTTP API integration scenario
tools/staging/verify-integrated-stage-app-storage.py created a local staged
file through authenticated LocalStorage, installed a real owner-labelled
container through authenticated stage AppManagement, read the staged
file from INSIDE the Docker container, and verified persistence after
stop, start and restart. Writing from inside the stage container was denied
by the read-only bind mount. Then the app and staged file were removed.
Before/after sets of 16 existing Docker production container IDs matched.

Observed:
LIVE_AUTHENTICATED_APPMANAGEMENT_LOCALSTORAGE_INTEGRATION_PASS
STAGED_STORAGE_PERSISTED_THROUGH_STOP_START_RESTART_PASS
STAGED_APP_STORAGE_READ_ONLY_ENFORCED_PASS
PRODUCTION_DOCKER_IDS_PRESERVED_PASS

This closes the specific staging manager/storage integration deficit, but
does NOT establish the separate full ReCasaOS AppManagement + LocalStorage
production APIs, public UX security, or full production-equivalent release.


## LIVE stage transaction recovery, not a production cutover

The v0.6.5 staging-only release also supports authenticated checkpoints,
restore, and interrupted undo-journal recovery for isolated stage file data.

- Checkpoint copies the private staged file tree to an immutable
  name-scoped, checksummed backup while the manager's exclusive lock
  prevents its own concurrent writes.
- Restore verifies bundle hashes and exact owned-app identities, writes
  and syncs a durable undo journal BEFORE changing data, stops only
  registered owned staging applications, restores data within the same
  bind-mounted folder inode, reactivates previously running stage apps,
  then closes the journal. An exception attempts the undo automatically;
  an interrupted transaction leaves a pending journal, which blocks
  unrelated staging app/storage actions until explicitly recovered.
- Dashboard offers checkpoint creation, restore, deletion and interrupted
  recovery controls; all operations require the same private bearer token.
- No production binds, Docker apps, CasaOS services, SSH config or user
  accounts can be selected by these endpoints.

End-to-end stage proof:
LIVE_STAGE_CHECKPOINT_CORRUPT_RESTORE_AND_DOCKER_REACTIVATION_PASS,
STAGED_PREEXISTING_DATA_RESTORED_AND_NEW_CORRUPT_FILE_REMOVED_PASS,
LIVE_INTERRUPTED_STAGE_RECOVERY_JOURNAL_ROLLBACK_PASS,
BLOCKED_UNSAFE_STAGE_APP_ACTIONS_UNTIL_UNDO_RESOLVED_PASS and
LIVE_STAGE_CHECKPOINT_DELETE_PASS. All existing Docker IDs preserved.

**No FULL PASS:** tests only concern constrained staging data, not complete
production filesystem/Compose recovery or verified in-place host cutover.
