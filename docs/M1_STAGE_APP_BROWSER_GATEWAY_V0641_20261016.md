# OpenServerDesk v0.6.41 — staging-only MySpeed browser gateway

Original dashboard MySpeed localhost addresses referred to the client device when opened remotely. This adds project-scoped same-origin routes without opening any new public ports.

- POST /api/v1/stage/app-web-session takes a registered project ID and a write-authorized Bearer token. Project, Docker ownership and running state are validated.
- The returned 600-second HttpOnly SameSite=Strict cookie is scoped only to /stage-app/<project>/, with at most 16 live sessions. Bearer token is never added to the app URL or sent upstream.
- Proxy routes are restricted to the verified MySpeed staging instance at its localhost-only Docker port. No caller-supplied external hosts/ports, no redirects to other hosts, no upstream cookies/Set-Cookie, bounded response/request sizes, and no service workers. Modifying requests enforce same-origin.
- The tested MySpeed SPA asset and API absolute routes are rewritten under its scoped project prefix; this is not a generic reverse proxy and does not claim WebSocket/SSE support.
- Dashboard adds Open app for the exact running MySpeed pilot, retaining existing operator permission.
- SECURITY LIMITATION: same-origin hosted app scripts are not strongly isolated from the dashboard origin; a separate isolated origin is needed for general untrusted app hosting.
- No CasaOS production change, data upload migration, external HDD reads, DNS changes or production cutover.
- Broader App Store feature parity and M1 acceptance remain open.
