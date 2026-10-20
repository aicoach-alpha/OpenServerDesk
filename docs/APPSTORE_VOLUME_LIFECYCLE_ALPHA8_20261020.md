# OpenServerDesk Alpha 0.7.0-alpha.8 — App Store Compatibility and Lifecycle

Delivered to parallel Alpha only. CasaOS production remains unchanged.

## App Store sandbox compiler
- Existing 726-entry CasaOS catalog, 654 static isolation plans (90.1%).
- 72 blocked: 67 unsafe targets, three unsupported dependencies,
  and two invalid services, as observed in the targeted gate.
- Normalize trailing slash on container mount destinations. Original CasaOS
  host bind source paths are never reused. Stage sources are freshly allocated
  under /opt/openserverdesk-dev/runtime-stage/stage-app-manager only.
- Support app data targets: /var/lib/postgresql/data, /var/lib/mysql,
  /home/node/.n8n, /etc/pihole, /root/.ollama.
- Reject docker.sock, /var/lib/docker, /var/lib/casaos, kernel trees,
  system identity files, and SSH/Docker credential paths.
- Up to 12 services and 64 stage-owned bind targets per project, max
  16 volumes per service. Immutable image ID, owner provenance, and
  isolated stage network are unchanged.
- Global hard cap: 16 compiled staging services; 256 MiB/service.
  Six stage project slots continue to apply. Budget checked before creating
  a new project or writing stage data.

## Unified application lifecycle
- Stage-owned Apps cards expose a compact Lifecycle menu.
- Start/Stop/Restart/Uninstall use the original role-checked stage APIs.
- Compiled projects additionally offer Update, Rollback when available,
  cold Backup when stopped, and Backup+Restart when running.
- Root-protected Qui stays inspect-only; recovery states hide mutation controls.
- CasaOS production application cards stay read-only.
- UI includes revision, rollback and checkpoint metadata with no secrets.

## Acceptance boundary
- Prior release: one real staging MySpeed instance passed install, stop,
  start, restart, uninstall; Docker per-container UAT is not repeated.
- Alpha 8: a single focused source/inventory safety gate passed.
- 654 is STATIC SANDBOX PLANNING only, not 654 functional runtime passes.
- Full CasaOS parity, original data import and cutover remain blocked.
- Weighted M1 acceptance percentage remains unchanged without proof.
- Public endpoint https://osd.vervue.my.id, origin 192.168.31.31:18691.


## Alpha 0.7.0-alpha.9 integration correction
- The authenticated stage-only MySpeed web gateway now permits POST/PUT/PATCH
  from the exact Cloudflare Alpha HTTPS origin osd.vervue.my.id and the
  already approved tailnet/LAN Alpha origins. No wildcard origin is accepted.
- Stage web preview session cookies use Secure when issued on Alpha.
- App Cards omit the stopped-only cold Backup control for a partially
  running multi-service project; operator must restore a consistent state.
- The project web gateway is intentionally **not** made generic for arbitrary
  untrusted catalog images. Broad web application runtime compatibility
  remains unproven until origin isolation and capability review are solved.
