# M1 actual application Debian package upgrade/downgrade — 2026-10-15

**One scoped release gate PASS.** The reproducible
`tools/staging/verify-application-deb-upgrade-rollback.sh` installs
`openserverdesk-m1-candidate_0.3.0_amd64.deb` into an isolated dpkg root,
upgrades the actual application package to `0.4.0`, then downgrades to `0.3.0`.

- 0.3.0: executable packaged UserService and installed OpenServerDesk API,
  no opt-in systemd service unit.
- 0.4.0: expected new systemd service unit installed and declared ExecStart
  targets the packaged read-only API. Package version confirmed.
- Rollback to 0.3.0: service unit removed; packaged executable and API bytes
  exactly match the initial 0.3.0 baseline SHA256 values.

Observed `APPLICATION_PACKAGE_UPGRADE_040_PASS` and
`APPLICATION_PACKAGE_ROLLBACK_030_PASS`.

The verification deliberately does not install to the host dpkg database,
start/stop production systemd services, migrate application volumes, or
claim full migration readiness. The previous attempt to exercise transient
host-level service activation was blocked by access safeguards, so this
gate proves packaging rollback only.
