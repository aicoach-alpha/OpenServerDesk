# M1 focused abrupt-process-kill recovery — 2026-10-15

The isolated packaged three-service staging runner now writes a persistent,
fsynced recovery journal before allocating its disposable containers or
Docker named volumes. Every created resource has an explicit random fixture
owner label; the isolated runner supports `--inject-sigkill-after-start`
for this single scoped fault-injection gate.

A new independent `tools/staging/recover-fullstack-orphans.py` verifies
the journal token and exact expected resource names; it confirms all
existing container/volume labels BEFORE deleting any resource. It removes
only matching owned test containers and volumes and reclaims the associated
validated scratch directory and journal.

Focused result: SIGKILL of the running staging test orchestrator occurred
after all three disposable services had started. A **new process** recovered
all exact test resources; no corresponding container, named volume, or
journal remained. `CRASHED_STAGING_STACK_RECOVERED_PASS` and
`FOCUSED_SIGKILL_RECOVERY_PASS` observed.

Limitations: recovery was explicitly invoked by the fresh process, not
automatically triggered by a dedicated always-on watchdog. This does not
prove kernel/power-loss durability, production service migration rollback,
or full M1 security audit. Production CasaOS was never changed.
