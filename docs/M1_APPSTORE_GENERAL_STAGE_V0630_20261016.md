# v0.6.30: CasaOS App Store general isolated staging installer

Date: 16 October 2026. Staging release only, production is unchanged.

Implemented FIRST, then random UAT (no repeated full-suite test loop):
- Read the local CasaOS App Store definitions and select a catalog app
  using its original, versioned image reference. Never execute the
  source Compose file, existing user bind paths, original port mappings,
  environment secrets or privileged host settings.
- Safe preflight for single-service apps: explicitly pinned image,
  supported target volumes, unprivileged execution, and a local image
  cache check. Multi-service and other unsupported arrangements are
  rejected, not silently called compatible.
- Operator can explicitly prepare a missing exact-version image from
  the source catalog into Docker image cache, with a minimum 8 GiB
  Docker filesystem headroom and a 1 GB post-pull image-size bound.
  Preparing an image never starts an app or changes existing containers.
- Eligible cached images can be installed in a newly generated staging
  Docker container. It has network mode none, no host ports, all
  capabilities dropped, no-new-privileges, non-root UID 1000:1000,
  a bounded memory/PID quota and stage-only volume mappings. Original
  named/bind volume source paths are intentionally NOT reused.
- Start, stop, restart and uninstall refer only to the exact full
  container ID in a private stage registry and reverify ownership,
  stage volume device/anti-symlink boundary, Docker labels, image,
  network isolation and mount paths before mutation.
- App Store dashboard includes per-app staging compatibility review,
  prepare image, isolated install and lifecycle actions.
- Package v0.6.30 SHA256:
  d5216cbe90c39c5d403e121d6abf5bccd02dfbdcaf7718d230752ef0dfb38b2e
- Clean build source Git SHA:
  7dff95ea817329547bf327ee53e49e419a54df1b
- Detached Ed25519 staging signature verified.
  Version-specific stage upgrade from v0.6.29 to v0.6.30 succeeded
  with stage-only rollback protection.

Random UAT AFTER implementation:
- MySpeed (default): eligible + exact image cached.
- Calibre-web (default): eligible for the restricted stage mode,
  exact image not cached.
- Healthchecks (github.com): refused, no explicitly pinned image.
- Snapotter (casaos.app): eligible for restricted mode, exact image
  not cached.
- Authenticated GET catalogue installation plan/list and HTTP 401
  unauthorized denial passed.
- Authenticated operator HTTP prepare cached MySpeed, install,
  stop, start and uninstall all passed; all 16 preexisting Docker
  container full IDs were unchanged afterward. Ephemeral staging UAT
  identities were removed.

Important: this is not full CasaOS App Store parity. Current general
installer is limited to eligible single-service catalog apps and exact
pinned images; prepared or installed apps have NO external network or
published host ports. This verifies isolated lifecycle mechanics, not
the public web interface or practical application functionality.
App-version update, reversible per-app data migration, user-facing
web networking, general multi-service catalog install, and final
security acceptance are not complete. Never claim those passed.

Production CasaOS (all six services) remains active and the
original Nextcloud user files on the HDD remain untouched.
The user-disabled recurring M1 progress jobs remain disabled.
M1 release acceptance score stays at 49% until an entire additional
acceptance milestone is verified. migration_allowed=false.
