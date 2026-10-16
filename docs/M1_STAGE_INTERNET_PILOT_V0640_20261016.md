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
