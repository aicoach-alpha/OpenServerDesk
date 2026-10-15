# M1 v0.5.0 full upstream component payload — 2026-10-15

**Single focused build and install verification: PASS.** This is not final
M1 production approval.

Previously, the M1 candidate .deb only included Gateway, MessageBus,
UserService and a read-only staging API. The new
`openserverdesk-m1-candidate_0.5.0_amd64.deb` additionally includes:

- ReCasaOS Core v0.4.73
- ReCasaOS AppManagement v0.4.68 and appfile2compose helper
- ReCasaOS LocalStorage v0.4.44
- ReCasaOS dashboard UI v0.4.87 (static assets, including index.html)

The existing pinned ReCasaOS Gateway v0.4.30, UserService v0.4.31 and
MessageBus v0.4.29 remain included. Version selections match official
ReCasaOS/CasaOS-Install release v0.5.27 components.lock.

**Supply provenance:** `tools/staging/m1-upstream-components.json`
pins each new release asset and its SHA-256 digest; offline builder
`tools/staging/build-m1-full-payload.py` rejects modified archives and
mismatched staged binaries. Archive payload files are selectively extracted
as regular files only into the dedicated OpenServerDesk package prefix.
Apache-2.0 component licenses and UI attribution NOTICE are included.

**Test evidence:** `tools/staging/verify-m1-05-full-payload.sh` installed
the exact package in a disposable dpkg root. Seven executables, UI index,
component notices and opt-in staging API unit were present. The packaged
Gateway served the packaged UI index over **isolated container loopback**,
without host port exposure, host systemd activation, or production mounts.
Observed `FULL_COMPONENT_INSTALL_AND_DASHBOARD_SERVE_PASS`.

**NOT proven:** startup/integration of upstream Core, AppManagement and
LocalStorage, complete dashboard functions, complete Docker/Compose and
external volume preservation, in-place activation/cutover rollback, and
verified signed production release + scoped security/pentest.

Release decision remains fail-closed in
`docs/M1_RELEASE_DECISION_AFTER_PAYLOAD_20261015.json`. This package is
not a production installer and must not be deployed over CasaOS.
