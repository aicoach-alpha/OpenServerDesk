# OpenServerDesk Alpha .47 — verified staging image names and version tags

## Implementation
- Stage-only Docker /images/json now publishes display RepoTags exclusively
  for exact curated, pinned catalog images whose locally cached tag resolves
  to the same immutable image ID already proven in a registered stage container.
- The approved sources are the exact digest-pinned Dozzle, Dockpeek,
  Glances and WUD catalogue pilots, plus the known MySpeed 1.0.8 staging
  pilot if that local tag still resolves to its installed immutable image.
- A tag that is changed, missing or points to a different image is omitted:
  the verified sha256 image digest continues to be shown. The container
  listing carries an optional sanitized osd.stage.catalog.image_tag label.
- Tag aliases are looked up only from a fixed source allowlist; no arbitrary
  image tags from production, host-wide Docker image enumeration, image
  pull, registry credentials, runtime host inspection or external network.
- /images/{digest}/json returns the same version alias in RepoTags.
  RepoDigests remains empty and Created/Size remain unknown zero defaults.
- App lifecycle and Docker event ImageID remain immutable and unchanged.
- Four focused new tests PASS covering WUD pinned tag, changed image
  digest refusal, fixed-allowlist forgery refusal, and actual current staging
  digest-alias consistency. No repeated full-suite or arbitrary Docker audit.

## Deployment and boundaries
- Release both Alpha and rootless broker from .47, preserving the systemd
  socket inode used by existing staging containers.
- WUD can display tagged stage images. External registry update checks,
  production inventory, arbitrary host Docker API and full CasaOS functional
  parity are not promised.
- 676/726 safe static plans unchanged. CasaOS production and the Nextcloud
  external HDD remain untouched; no production cutover.
