# OpenServerDesk 0.6.40: stage-only internet-capable MySpeed pilot

Authentic diagnosis:
- MySpeed from original CasaOS default:MySpeed, immutable germannewsmaker/myspeed:1.0.8 cache failed in compiled internal-only network with exit code 1, no OOM.
- A separate short-lived diagnostic container using exact cached image, distinct stage-owned bind volume, bridge networking and sandbox caps ran through the same startup period and logged Server listening on port 5216. That container was removed immediately.
- Therefore lack of outbound networking is the confirmed compatibility delta; full application HTTP and lifecycle UAT still required.

Implemented guardrails:
- Only original exact catalogue ID default:MySpeed, exact image tag germannewsmaker/myspeed:1.0.8, single service myspeed, and original network_mode: bridge can use outbound user-defined Docker network.
- All other catalog apps remain on the internal-only bridge. Immutable cached image, cap_drop all, no-new-privileges, UID1000, resource limits and loopback-only host port remain enforced.
- Docker provenance checks the exact stage-owned Compose bridge network, Internal flag, driver and labels through lifecycle operations and cleanup.
- A user-defined outbound bridge can access destinations reachable through host routing, potentially including private LAN addresses. This pilot is NOT a private-LAN egress firewall. Production firewall, networks and Compose projects unchanged.
- Dashboard labels network scope and avoids suggesting a remote user's localhost resolves to the staging server.
- Limited pilot is not general CasaOS network parity. Production replacement remains prohibited.

## Authentic post-deployment staging UAT, 16 Oct 2026
- Signed packaged v0.6.40 activated; staging /health version matched v0.6.40.
- Docker Compose compiled install: default:MySpeed, exactly one service and a dedicated project-scoped outbound bridge, service remained running after 11-second startup observation.
- Stage server loopback application HTTP GET returned 200 with HTML.
- Stop and start: PASS; HTTP returned 200 after start.
- Restart: PASS; HTTP returned 200 after restart.
- SQLite cold checkpoint: PASS; exactly one database passed quick-check.
- SQLite checkpoint restore on stopped stage app: PASS; checksum plus one SQLite quick-check passed; HTTP returned 200 after starting again.
- Update with unchanged original catalogue image/config: returned no_change; replacement update and image rollback across revisions were NOT tested.
- Uninstall: removed owned containers and dedicated network, left an empty registry, with stage data retained.
- Reinstall: new generated project, outbound pilot running, HTTP returned 200.
- Real single-app lifecycle UAT therefore PASS for install/stop/start/restart/checkpoint/restore/uninstall/reinstall. Multi-service parity, revision upgrade/rollback, remote browser access and LAN egress filtering remain open.
- One MySpeed staging project intentionally remains running for UI inspection. It uses Docker resources on the shared staging host but does not replace an existing production Compose project.
- Accepted M1 progress stays 49% because production-equivalent AppManagement/LocalStorage is not fully demonstrated.
