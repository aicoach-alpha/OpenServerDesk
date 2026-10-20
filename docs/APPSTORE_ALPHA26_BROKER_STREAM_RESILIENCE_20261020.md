# OpenServerDesk Alpha 0.7.0-alpha.26 — Dozzle stream resilience

## Implemented
- Stage-only synthetic Docker /events stream uses a 600-second upper bound
  with a JSON whitespace heartbeat every 9 seconds. This reduces unnecessary
  event-stream reconnection every 38 seconds.
- Docker stats streams are bounded at 180 seconds. Live stage-only
  CPU/memory snapshots are cached up to 7 seconds per verified immutable
  container ID, reducing repeated Docker CLI metric collection.
- The provenance-checked staging container list remains deduplicated (3s TTL).
  Metrics cache is limited to 16 entries and rejects untrusted staging labels,
  IDs and non-stage applications. Stopped containers bypass the cache.
- The real host Docker socket, CasaOS production, Nextcloud HDD and
  external user data remain unavailable to untrusted Dozzle containers.
- Four cache/provenance assertions plus targeted event/log contracts PASS.

## Completion boundaries
- A single real Dozzle staging UAT must still confirm log/browser listing.
- 673 of 726 app definitions have safe staging plans; 53 require separate
  capability-scoped adapters. This is not proof of complete functional parity.
- CasaOS production remains unchanged; no production cutover.
