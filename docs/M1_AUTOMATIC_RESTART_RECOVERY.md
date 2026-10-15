# M1 targeted automatic recovery at next staging orchestration startup — 2026-10-15

The packaged three-service staging runner now acquires an exclusive, nonblocking
staging file lock for the whole invocation. Before launching any new fixture,
it scans its own persistent journals and invokes the already verified orphan
recovery routine for each validated journal token. A competing instance fails
closed. This prevents concurrent staging runs from deleting each other's
active fixture resources.

One focused test used SIGKILL immediately after the three disposable services
started, then invoked the SAME runner's startup path with --recover-only.
The startup path recovered the abandoned fixture containers and six volumes
without manually calling the separate recovery script. The journal and owned
resources were absent afterward.

Observed: CRASHED_STAGING_STACK_RECOVERED_PASS,
AUTOMATIC_RESTART_RECOVERY_PASS,
ONE_SIGKILL_RESTART_RECOVERY_GATE_PASS.

Scope: automatic when the staging runner is invoked again; this is not an
always-on OS watchdog or proof of power-loss durability. Production services
and real application data remain untouched. M1 migration readiness stays
blocked until full real migration rollback and security gates are proven.
