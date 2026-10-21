# OpenServerDesk Alpha 0.7.0-alpha.49 — Homepage stage-only pilot

## Implemented
- Exact digest-pinned BigBear/CasaOS Homepage v2.4.0 catalog adapter.
  Only github.com:com.bigbeartechworld.homepage with its exact original
  image, TCP port 3000, one /app/config data volume and one Docker socket
  can use the facade. Privilege/device/host network/command/digest or
  any source volume change blocks approval.
- Original /DATA/AppData/$AppID/config content is NEVER mounted, copied
  or inspected. Its target is remapped to new, isolated stage-owned storage.
- Original /var/run/docker.sock is NEVER mounted. The adapter injects
  the existing synthetic stage-only read-only Docker metadata API socket.
- App launches as 1000:1000 with no caps, no-new-privileges, isolated
  Docker network, bounded memory/PIDs, no external registry access, and
  no access to production CasaOS apps.
- HOMEPAGE_ALLOWED_HOSTS is pinned to localhost:3000, matching the
  authenticated stage web gateway upstream Host header. Neither a wildcard
  nor the public production domain is approved in the container env.
- Authenticated gateway rewrites root-relative /_next/ JavaScript and CSS
  paths into each specific stage-app namespace. No generic arbitrary
  upstream host routing or proxy access is permitted.
- Initial startup receives a bounded 30-second window, the existing
  maximum used for curated slower-starting Glances. Others unchanged.
- Five focused static/compiler/environment/gateway/catalog tests PASS.
  Real image install and HTTP UAT remains to be checked after release.
- Safe static sandbox plans: 677/726; 49 still require scoped integration.

## Explicit compatibility limitations
- Fresh empty Homepage config is not an import of CasaOS user dashboard,
  saved settings, credentials, or system integrations.
- Docker widgets can only discover the subset of already verified,
  registered stage-owned containers through the synthetic read-only API.
- Next.js routing and interactive browser functionality require explicit
  runtime UAT; compilation alone is NOT functional parity.
- CasaOS production remains active; no cutover and no external Nextcloud
  user HDD or original CasaOS production volume operations.
