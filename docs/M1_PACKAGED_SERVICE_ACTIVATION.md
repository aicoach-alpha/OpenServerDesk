# M1 packaged real UserService activation gate — 2026-10-15

**Single focused gate PASS:** `tools/staging/activate-packaged-user.py`
installs the existing `openserverdesk-m1-candidate_0.3.0_amd64.deb`
into an isolated dpkg root, rejects unexpected Debian control hooks,
then launches the **actual UserService executable from the installed package**
in a disposable locked-down Docker container.

The original `osd-m1-user` staging container was stopped only while the
disposable candidate was using the staging Gateway/MessageBus network.
Synthetic account registration and login through routed
`/v1/users/register` and `/v1/users/login` both succeeded.
The candidate container was removed, the original staging UserService
restarted, and routed status confirmed the original initialized state.
All six existing CasaOS/Docker/OpenServerDesk staging systemd units active.

This verifies real packaged UserService staging activation, isolation, and
functional restoration. It does NOT prove packaged Gateway/MessageBus
activation, automatic full application/volume rollback, production migration,
or mandatory M1 security pentest. No production CasaOS service or data
was touched; migration readiness must remain locked.
