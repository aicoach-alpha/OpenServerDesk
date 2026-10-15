# M1 focused restored-stack activation failure cleanup — 2026-10-15

One fault-injection scenario was run using the existing isolated packaged
Gateway + MessageBus + UserService stack with disposable Docker named volumes.
The runner now supports the explicit test-only argument
`--inject-restored-activation-failure` immediately after attempting
activation of the restored three-service stack.

Observed: the injected activation failure produced a nonzero result;
the cleanup handler removed all newly created containers and owned fixture
volumes. Pre/post lists of named fixture resources matched, and all three
original staging containers remained running.

PASS: automatic cleanup of resources on a **handled process exception**.
NOT proven: host crash, SIGKILL, power loss, restoration of production
containers, or complete real-world migration rollback. Production migration
readiness remains closed.
