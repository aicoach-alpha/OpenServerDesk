# M1 focused staging .deb install / upgrade / rollback — 2026-10-15

Existing real Debian packages:
- openserverdesk-migration-tools_0.1.0_all.deb
- openserverdesk-migration-tools_0.2.0_all.deb

Created a separate disposable dpkg installation root and dpkg status
database under /opt/openserverdesk-dev/runtime-stage, never the live host.
With `dpkg --root=STAGING_ROOT --install`, verified:
1. Install 0.1.0 — package database and installed VERSION both read 0.1.0.
2. Upgrade to 0.2.0 — both read 0.2.0.
3. Roll back by downgrading to 0.1.0 — both read 0.1.0.
4. Installed openserverdesk-preflight script is executable.
5. All six CasaOS, Docker and OpenServerDesk staging systemd units active.

PASS: real .deb package-manager install/upgrade/downgrade behavior in a
separate staging root. The tested .deb provides migration tools, not a full
replacement server with all application containers and persistent volumes.
Do not treat this as full migration/rollback readiness or security PASS.
