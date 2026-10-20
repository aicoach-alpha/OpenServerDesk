# Alpha 0.7.0-alpha.19 — real curated Dozzle staging UAT receipt

## Verified on andre-nas
- Exact digest-pinned catalog Dozzle image prepared into the existing Docker
  image cache. No production container was modified.
- A fresh stage-owned project osd-compiled-ba7e9c4d6ce0 installed with a
  synthetic Docker API facade Unix socket (not the host docker.sock).
- The stage service was running and passed the engine provenance checks.
- The host loopback port was *not* reachable, as expected on Docker's
  internal-only staging network. The verified PRIVATE container endpoint
  (derived from the registered project+container ID, never user URL)
  returned HTTP 200 and HTML for the Dozzle application root page.
- The read-only broker had separately returned only staging container metadata;
  POST and DELETE were rejected HTTP 403.
- The temporary Dozzle stage project was uninstalled successfully.
  The two original registered stage projects remain; no recovery pending.
- These are **runtime install, private HTTP and uninstall** passes. They are
  NOT proof of fully functioning Dozzle logs, browser asset rewriting,
  WebSocket streaming, or generic CasaOS app parity.
- Original CasaOS production and Nextcloud external user HDD data were not
  accessed, stopped, copied, migrated or replaced in this UAT.

## Boundaries still open
- Synthetic Docker API facade does not export stage logs; Dozzle's primary
  log viewer is therefore not functionally equivalent to production Dozzle.
- The approved pinned image digest is in the local cache for future tests.
- The 673/726 number is static planning coverage; remaining 53 definitions
  still require capability-scoped integrations or reduced functionality.
- CasaOS production cutover is not approved.

## Git/release
- Source release 0.7.0-alpha.19; app and broker are both user systemd
  services running as andre uid1000.
- Public endpoint https://osd.vervue.my.id and origin 192.168.31.31:18691.
