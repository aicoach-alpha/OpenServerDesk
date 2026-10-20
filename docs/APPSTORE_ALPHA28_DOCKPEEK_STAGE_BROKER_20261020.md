# OpenServerDesk 0.7.0-alpha.28 — second host adapter pilot (Dockpeek)

## Implemented
- Read-only stage Docker compatibility socket extended ONLY to two exactly
  pinned local CasaOS catalogue manifests: Dozzle and Dockpeek.
- Dockpeek: github.com:com.bigbeartechworld.dockpeek,
  image ghcr.io/dockpeek/dockpeek:v1.7.2 with the exact catalogue
  sha256 digest, service big-bear-dockpeek.
- Refuse alternative image tags/digests, privileged containers, devices,
  host network modes, additional bind mounts or unfamiliar app IDs.
- Source host docker.sock NEVER imported. Only synthetic stage-owned
  Docker metadata/logs/stats/events API can be seen by approved containers.
- No Docker write operations, raw host filesystem access, or Nextcloud HDD.
- Both curated broker pilots reject switching to arbitrary image versions.
- Catalog safe static stage plans 674/726; 52 still require scoped adapters,
  unsupported Compose metadata zero.
- Four focused Dockpeek tests PASS, plus broker and catalog
  classification contracts PASS.

## Lifecycle acceptance
- Real Dockpeek staging install/web/uninstall is a separate narrow UAT
  required before claiming browser/runtime compatibility.
- Host integration broker remains DENY by default for the remaining apps.
- Do not cut over CasaOS production; stage isolation intact.
- Deployment: https://osd.vervue.my.id, origin 192.168.31.31:18691,
  user-level systemd services as andre UID1000.
