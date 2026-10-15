# M1 focused packaged Gateway + MessageBus activation — 2026-10-15

One gate verified by tools/staging/activate-packaged-gateway-bus.py:
- Installed existing openserverdesk-m1-candidate_0.3.0_amd64.deb inside a
  disposable dpkg root, without maintainer-script activation.
- Started the actual packaged Gateway binary in a constrained Docker container
  with --network none and no published host ports.
- Routed loopback HTTP GET /ping succeeded inside that container.
- Started actual packaged MessageBus binary sharing only the candidate Gateway
  container network namespace. Used disposable configs, runtime, bus database
  and log directories, never production or the existing staging run directory.
- Registered one synthetic MessageBus event using the temporary container's
  own internal authentication secret; request succeeded.
- Removed both disposable containers, verified candidate containers absent.
- Existing staging Gateway/MessageBus/UserService containers were not stopped.

Result: PACKAGED_GATEWAY_PING_PASS,
PACKAGED_MESSAGEBUS_EVENT_PASS,
PACKAGED_GATEWAY_BUS_CLEAN_ROLLBACK_PASS.

PASS scope is isolated packaged binary activation and teardown, not production
replacement, system service auto activation, complete persistent volume restore,
crash/power-loss recovery or final M1 security pentest. Production migration
readiness remains false.
