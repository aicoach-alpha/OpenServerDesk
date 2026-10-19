# OpenServerDesk v0.6.47 — verified private bridge web and install finalization

The first authentic CasaOS Qui + PostgreSQL staged install initialized both services, and both Docker healthchecks ultimately reported healthy, but the 11-second readiness timeout failed because an internal-only Docker bridge does not forward host loopback published ports.

- Authentic diagnostic: loopback published Qui port returned connection refused, while a direct HTTP request from the Docker host to the Qui container's isolated bridge IP on port 7476 returned HTTP 200.
- Runtime now resolves the active target private IP only through Docker inspect of its fully ownership-verified stage container; the inspected container must have exactly the expected project-scoped internal bridge network and a valid private IPv4 address.
- For internal-only compiled apps, readiness checks use the verified private address and container target port instead of falsely requiring host-loopback NAT. Outbound MySpeed keeps existing loopback semantics.
- Application web sessions use the same authenticated, time-limited and project-scoped stage gateway; Qui resolves dynamically to its inspected private Docker address and never exposes the private IP in the browser URL. No arbitrary remote URL/host input is accepted.
- New explicit finish-install action confirms the ready late-started, exact Qui staged project recorded by a previous pending install journal, writes its registry entry, then clears the journal. Other pending installs still use existing failure recovery.
- Fresh Qui install has a longer 25-second startup grace for DB initialization. The original service and PostgreSQL healthcheck/privileged restrictions remain unchanged.
- Not a generic remote app reverse proxy and not a production release; old CasaOS production remains in service and user Nextcloud volumes are not accessed.

## Authentic corrected staging UAT evidence
- Host to verified internal Docker private IP Qui port 7476 returned HTTP 200; published 127.0.0.1 port returned connection refused on this internal-only bridge.
- Signed packaged v0.6.47 deployed without production changes. finish-install rechecked stage-owned container provenance and readiness, committed the earlier Qui project and cleared its install journal.
- Both real services Qui and PostgreSQL reported running=true and health=healthy, after installed project became visible alongside unchanged MySpeed.
- Stage browser gateway authenticated-session logic returned Qui HTML over the internal private Docker address: HTTP 200 and 3662 response bytes.
- One focused authentic restart exercised start-order postgres then qui; both services returned healthy and Qui gateway again returned HTTP 200. No pending recovery journals remained.
- Unit tests: three new targeted private endpoint/session/readiness tests PASS. No broad re-run of prior suites.
- Container private IP stays inside the gateway, not in browser URL. User-origin authenticated browser navigation and untrusted multi-app gateway isolation remain separate future acceptance work.
- Production CasaOS and external Nextcloud user files were not migrated.
