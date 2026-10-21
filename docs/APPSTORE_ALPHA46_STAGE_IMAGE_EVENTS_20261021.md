# OpenServerDesk Alpha 0.7.0-alpha.46 — event image consistency

## Delivered
- Synthetic Docker lifecycle events (container start/die/destroy) now
  report the same immutable stage-verified image digest as the
  /containers/json, /containers/{id}/json, /images/json and
  /images/{digest}/json read-only endpoints.
- Event generation rejects a row unless its stage-only scope, Image and
  ImageID provenance agree and the digest has exact sha256:64hex format.
  It never forwards host Docker events or arbitrary user-supplied images.
- Focused five-test event/stats gate passed, including a forged event
  payload refusal. Existing event stream resource/time bounds remain.
- Both Alpha UI and broker deploy together; stable systemd socket inode
  remains pinned across broker restart, with no Docker socket migration.
- This gives WUD and other approved stage-only monitors internally
  consistent image identity in list/detail and container event payloads.

## Still intentionally unsupported
- Registry update lookups, host image enumeration, image creation/deletion,
  arbitrary Docker API writes or production Docker socket access.
- Static sandbox plans 676/726; full WUD and CasaOS application parity
  still require feature-specific evidence before any production cutover.
- CasaOS services, original production containers and external Nextcloud
  HDD data remain untouched.
