# M1 package runtime activation — 2026-10-15

**One focused gate PASS.** The updated builder now produces
`openserverdesk-m1-candidate_0.4.0_amd64.deb`, retaining real
Gateway, MessageBus and UserService binaries and the OpenServerDesk Python API.

It also installs the opt-in, hardened systemd unit
`/usr/lib/systemd/system/openserverdesk-m1-candidate.service`.
The unit binds only to 127.0.0.1:18692; it is not enabled, started or
restarted automatically by the package and has no maintainer hooks.
It does not touch existing CasaOS production services.

Focused real validation: dpkg-installed package into an isolated root,
launched the **installed** API source on an ephemeral loopback port,
verified /health, read-only capabilities and POST HTTP 405, then stopped
the isolated process. `DEB_040_INSTALLED_READONLY_API_LIVE_PASS`.

Remaining blockers: full app service lifecycle/cutover rollback and mandatory
M1 final security gate. Production migration_allowed remains false.
