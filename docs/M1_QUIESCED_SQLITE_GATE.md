# M1 focused UserService quiesced SQLite snapshot gate — 2026-10-15

Performed one integration rehearsal on existing isolated ReCasaOS staging:
- Before quiescence, the staged SQLite user DB passed PRAGMA integrity_check.
- Stopped **only** Docker container osd-m1-user.
- Created a SQLite snapshot using tools/migration/sqlite_fixture_snapshot.py,
  in a dedicated staging directory under /opt/openserverdesk-dev/runtime-stage.
- Verified the staged snapshot using SQLite PRAGMA integrity_check: PASS.
- Restarted UserService staging; routed /v1/users/status through staged Gateway:
  PASS, account state initialized; Message Bus websocket resubscription PASS.
- CasaOS, CasaOS Gateway, CasaOS UserService, CasaOS MessageBus, Docker and
  OpenServerDesk staging systemd units stayed active.

PASS: staged service quiescence, SQLite snapshot integrity, and service/API
recovery. NOT YET PASS: applying a database rollback, whole-app/volume
restoration, controlled package activation, power loss, or M1 security pentest.
No production services or databases were stopped or modified.
