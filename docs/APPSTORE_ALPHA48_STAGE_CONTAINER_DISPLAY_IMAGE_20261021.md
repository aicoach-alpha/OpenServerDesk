# OpenServerDesk Alpha .48 — consistent stage-only image display identity

## Delivered
- The Docker-compatible GET /containers/json now uses an approved
  locally digest-verified catalog name:version in its Image field.
  ImageID remains the exact immutable SHA256 image ID verified against the
  running container and staged installation manifest.
- Container GET /containers/{id}/json retains the immutable Image field
  and uses Config.Image as the verified display tag when available.
- Read-only lifecycle event Actor.Attributes.image and from fields use
  the same display tag, with osd.stage.immutable_image retaining its SHA256
  digest for provenance and correlation.
- When the tag is missing, retargeted or no longer matches the installed
  image, all fields fall back to immutable image ID, never a guessed version.
- The accepted tags remain fixed and locally resolved only for curated
  Dozzle, Dockpeek, Glances, WUD and MySpeed pilot source references.
- Four targeted tests passed: tag consistency, alias forgery denial,
  Unix-socket container list/detail compatibility, and actual staged
  container immutable ID. No full-catalog or production Docker audits.
- Existing registry update checks and image writes remain unavailable.

## Security and release scope
- Both alpha and rootless broker use the same .48 release and existing
  systemd-owned Unix socket inode, without mounting the host Docker socket.
- 676 of 726 apps have safe static sandbox plans; no claim of all-runtime
  parity, CasaOS production cutover or external Nextcloud HDD migration.
