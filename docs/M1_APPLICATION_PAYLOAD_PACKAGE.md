# M1 focused Debian application payload candidate — 2026-10-15

Created the non-activating candidate `openserverdesk-m1-candidate_0.3.0_amd64.deb`
using `tools/staging/build-m1-candidate.sh`.

Included actual staged ReCasaOS binaries for Gateway, MessageBus, UserService,
plus OpenServerDesk API source app.py and readiness.py. No post-install hooks
or systemd changes. Rebuild requires the previously staged binaries.

Focused dpkg test performed inside a separate temporary root with its own
package database. The candidate installed, package version 0.3.0 and binary
execute permissions were verified, and `dpkg --root ... --purge` removed the
candidate payload. Both checks PASS.

This is a payload packaging milestone only, NOT a complete installer.
Service activation, config, credentials, DB and Docker volumes, upgrade
or rollback of running servers and mandatory M1 security gate remain open.
Production remains untouched; migration readiness stays locked.
