# M1 isolated Docker container rollback rehearsal — 2026-10-15

A disposable Docker container `osd-m1-rollback-fixture` with `--network none`,
read-only root filesystem, dropped capabilities, memory and PID caps, and one
fixture bind-mounted file was used. A snapshot held `baseline-v1`. After
changing the source file to `bad-upgrade-v2`, the container was stopped,
the snapshot restored, and the container restarted.

Observed: container running again; baseline file read from both host staging
fixture and inside container matched `baseline-v1`. Temporary container was
removed. Six CasaOS/OpenServerDesk/Docker system services stayed active.

PASS: synthetic container stop/restart and fixture-data rollback.

NOT PASS: real ReCasaOS service version upgrade/rollback, network and route
recovery, database schema migration/rollback, Docker volume or Compose
project restoration, production-equivalent migration/activation, disaster
recovery, or M1 security gate. This test does not change migration_allowed.
