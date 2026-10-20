# OpenServerDesk Alpha 0.7.0-alpha.22 — stable Dozzle broker socket

## Delivered
- Stage-only Docker events, bounded real staging container stats, and
  exact staging-only 12-64-character Docker container ID resolution from
  the prior Alpha 0.7.0-alpha.21 implementation.
- User-level systemd .socket unit now owns the Unix socket file. It keeps
  the same inode across Python broker service restarts, so long-lived
  Docker bind-mounted Dozzle instances do not retain orphaned socket inodes.
- The Python broker validates systemd LISTEN_FDS=1 and LISTEN_PID, fd 3
  address/type, file owner UID1000 and mode 0600. Any mismatch fails closed.
- The service Requires and orders after its socket unit; Alpha remains
  a separate systemd user service as UID1000, not root.
- No broad host Docker API, privileged container access, real Docker socket,
  CasaOS production mutations, or Nextcloud external HDD access.
- Three focused socket activation tests PASS; event/stats and log APIs
  previously passed their focused contracts.

## Open parity boundaries
- Dynamic events and metrics are staging-only, with bounded streaming
  sessions; Dozzle browser log functionality still requires actual UAT.
- 673 of 726 CasaOS definitions support safe sandbox planning; remaining
  53 require separate capability-scoped adapters.
- CasaOS production cutover is not permitted or planned at this release.
