# Alpha 0.7.0-alpha.21 — Dozzle Stage Events and Stats Compatibility

## Implementation
- Docker API facade accepts 12-to-64-hex container references ONLY when
  each prefix matches exactly one provenance-verified staging container.
  Other IDs including production cannot resolve or inspect.
- GET /events emits stage-only synthetic container lifecycle JSON events,
  no real host Docker event stream. The request and output are bounded,
  limited to two concurrent subscribers and an 18-second session.
- GET /containers/{stage_id}/stats returns a bounded read-only staging
  snapshot. Docker CLI stats is called on the immutable confirmed ID only.
  CPU percent, memory usage and PIDs come from stage-only CLI metrics;
  process/network/host internals remain hidden. The Docker-shaped CPU
  cumulative values are derived for client compatibility, not original
  kernel CPU counters. Streaming stats sessions expire after 16 seconds.
- GET /containers/{stage_id}/logs remains bounded to 160 lines, 64KiB and
  5.5 seconds, with two concurrent stage-only readers.
- All mutations and unapproved Docker API endpoints remain HTTP 403.
  No host daemon socket or Nextcloud external HDD is passed to Dozzle.
- Four focused tests PASS for prefix uniqueness, untrusted queries,
  Unix socket event/stats payloads, and actual stage-only metric reads.

## Explicit limits
- The adapter only emulates the read APIs Dozzle needs; it is NOT a
  substitute for an unrestricted Docker daemon. Event/stats follow windows
  intentionally close and require client reconnection.
- Actual Dozzle frontend log rendering and reconnection must be evaluated
  in a single real staging UAT; static tests do not establish parity.
- Safe static catalog plans: 673/726; another 53 host-requiring apps remain
  restricted. CasaOS production and Nextcloud external user data untouched.
- Cutover to OpenServerDesk production is not authorized.
