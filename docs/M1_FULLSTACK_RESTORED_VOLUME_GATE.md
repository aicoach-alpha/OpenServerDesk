# M1 focused isolated packaged three-service stack recovery — 2026-10-15

Focused implementation: \`tools/staging/verify-fullstack-volume-rollback.py\`.

One end-to-end integration scenario uses **actual binary payloads** from
\`openserverdesk-m1-candidate_0.3.0_amd64.deb\`: ReCasaOS Gateway,
MessageBus, and UserService, all in disposable constrained Docker containers
with Gateway \`--network none\`, no published host ports and no production mounts.

- Gateway, MessageBus, and UserService start in a fresh isolated stack.
- Synthetic user registration and login succeed through its own Gateway.
- A synthetic \`local-storage\` event is registered in the isolated MessageBus.
- All three containers are removed (no active writers).
- UserService and MessageBus Docker named volume data are copied into separate
  backup named volumes.
- The stopped synthetic source \`user.db\` is intentionally damaged.
- The two backup volumes are restored into **new** Docker named volumes.
- The three packaged services start using the two new restored volumes.
- The original synthetic credentials log in successfully.
- UserService's MessageBus WebSocket subscription is verified in logs.
- All disposable containers and all six newly created, ownership-labelled
  Docker named volumes are removed. Original staging containers untouched.

Observed:
\`RESTORED_PACKAGED_THREE_SERVICE_STACK_AUTH_AND_BUS_PASS\`
and \`ISOLATED_STACK_AND_VOLUMES_CLEANED_PASS\`.

This verifies an isolated three-service application/data recovery scenario,
**not** live CasaOS cutover, full application/Compose volume coverage,
permissions/xattr fidelity across hosts, disk-failure/power-loss durability,
or full M1 security audit/pentest. Do not unlock migration readiness.
