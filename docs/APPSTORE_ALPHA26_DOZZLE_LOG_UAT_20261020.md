# OpenServerDesk Alpha 0.7.0-alpha.26 — Dozzle real log API PASS

## Implemented
- Docker log time parser treats validated negative Unix zero-time values,
  including nanosecond fractions from Go clients, as no date boundary.
- This closes an actual Dozzle v11.1.1 log retrieval HTTP 500. The real
  Dozzle backend GET /api/hosts/no-host-runtime/containers/{stage-id}/logs
  returned HTTP 200 with 6,346 bytes after the corrected parser.
- The temporary diagnostic logged only redacted timestamp *shapes* and
  was removed from source before this release; no query values were stored.
- Unix socket is owned by systemd, UID 1000, 0600; broker restarts keep the
  socket inode and existing stage container mount stable.
- Dozzle staging UAT confirmed app HTML 200, a nonempty containers-changed
  SSE payload with stage-owned ID and CPU/memory data, and real backend logs.
- Docker mutations, host secrets, production containers and user Nextcloud
  data remain inaccessible through the read-only adapter.

## Remaining boundaries
- Tests prove the log API backend and SSE, not a user-driven graphical
  browser session across every Dozzle view.
- The synthetic broker is not a full Docker daemon API and does not allow
  container creation, deletion, process execution or host mounts.
- 673/726 CasaOS definitions have safe static plans; 53 host-related apps
  still need separate scoped adapters. Production CasaOS cutover is not PASS.
