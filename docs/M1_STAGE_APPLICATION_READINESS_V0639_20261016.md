# OpenServerDesk v0.6.39 — real Docker lifecycle startup acceptance

An authenticated, isolated staging installation of the *real* cached CasaOS
default:MySpeed image via the v0.6.38 compiled runtime created the single
stage service successfully, but exited with exit code 1 approximately seven
seconds after initial startup. The published loopback HTTP port did not respond.
This must not be scored as successful functional installation. Original CasaOS
catalogue metadata indicates bridge network, while stage uses an isolated
internal Docker network; network egress compatibility is an unresolved
hypothesis, not a proven cause of this crash.

New runtime behavior:
- On install/update/restart/start, verify complete ownership using Docker
  labels, immutable images, exact container IDs, and stage-only mounts.
- Observe continuous service readiness for 11 seconds instead of accepting
  an instantaneous Docker "running" state.
- For published app web ports, require a successful TCP connection to the
  actual loopback port at the end of the observation period.
- Reject early exit and failed web readiness. Existing durable journals
  remain in place to permit scoped recovery after install/update failure.
- Expose stage-owned service status, numeric exit code and OOM indicator on
  the authenticated dashboard without revealing application logs.
- Do not change production containers, original bind paths, external storage,
  network policies, or the CasaOS service configuration.

These checks are not a substitute for sustained uptime, HTTP functional
acceptance, database integrity or full multi-service parity. Application
runtime compatibility still requires remediation. Do not raise the accepted
49% milestone or authorize CasaOS replacement on this evidence alone.
