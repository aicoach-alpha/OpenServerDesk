# M1 UserService staged activation failure and recovery — 2026-10-15

Executed on the actual ReCasaOS staging Gateway, Bus, and UserService setup;
production CasaOS systemd services and databases were not altered.

- Recorded SHA256 of the existing isolated staging UserService SQLite file.
- Temporarily stopped only the staging UserService container.
- Launched a disposable, constrained container as an intentionally failing
  activation candidate. The candidate exited with expected exit code 42.
- Removed the failed candidate and restarted the original staged ReCasaOS
  UserService container.
- Compared database SHA256 before/after: identical.
- Verified /v1/users/status through the staging Gateway and confirmed
  Message Bus WebSocket subscription in UserService logs.
- Checked six CasaOS/OpenServerDesk/Docker system services: all active.

Observed PASS: failure detection, original service restoration, SQLite
persistence, route recovery, Message Bus resubscription.

Not tested: two distinct real upstream binary releases, automatic activation
controller, schema upgrade/downgrade, Compose volume recovery, production-equivalent
migration, complete automated rollback, or scoped M1 penetration testing.
The fail candidate was deliberately synthetic; never call this a real
cross-version upgrade/rollback PASS. Migration remains prohibited.
