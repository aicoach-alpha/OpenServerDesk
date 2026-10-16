# OpenServerDesk v0.6.28: native CasaOS App Store installation pilot

16 October 2026, OpenServerDesk STAGING ONLY. Not a production CasaOS
replacement. Scope remains restricted to a single preapproved store app.

Real catalogue source: the already installed CasaOS default App Store
metadata for MySpeed, using exact image germannewsmaker/myspeed:1.0.8.
The original image was pulled as a Docker image-cache addition, without
replacing, restarting, deleting, or altering any production container.

Implemented:
- A dedicated stage Store Pilot API at /api/v1/stage/casaos-store-pilot
  and an operator-only pilot install control in the native App Store UI.
- Pilot supports only default:MySpeed. Any unapproved app ID is rejected.
  The exact image version is checked against the original CasaOS YAML.
  No original Compose service, environment or host data path is executed.
- The app runs under a random stage-owned Docker container identity.
  Network mode none, no host ports, no privileged mode, all capabilities
  dropped, no-new-privileges, numeric non-root UID:GID 1000:1000,
  memory and process limits, and exactly one dedicated stage-owned
  application data mount at /myspeed/data. This version needs a writable
  *ephemeral container filesystem* to initialize, but no existing host
  app directories are exposed.
- Each start/stop/restart/uninstall operation verifies the immutable
  Docker ID, stage-owner labels, network/port restrictions and expected
  data mount first. Uninstall retains staging data, never user HDD data.
- The engine was tested directly against the original app image:
  install, stop, start, restart, uninstall all PASS.
  Exactly 16 original Docker container IDs remained unchanged.
  On a failed initial start, the new staging container was removed,
  without touching original containers.
- Five test cases for image version provenance, malicious store symlinks,
  wrong tags, unapproved app IDs and path isolation all passed.
- Package v0.6.28 built from clean Git SHA
  6dc1ef20ed4c538a0ed220ba03cf2a66278f765b.
  SHA256: 9796f5ad85e6779abc4dcab38688b7ebf42d6ce9c0883da3e99a765fa6d93658.
  82 clean-source unit tests PASS. Detached local staging Ed25519
  manifest signature verified. Version-specific controller upgraded
  only the OpenServerDesk staging service from 0.6.27 to 0.6.28,
  with rollback on failed health checks.
- The live staging health API returns version 0.6.28.
  Unauthenticated GET to the pilot returns HTTP 401.
  All six original CasaOS production services remained active.

Important LIMITATION: A complete HTTP-based real install/stop/start/
uninstall UAT was attempted but not executed due an execution-tool safety
block. Therefore the stage UI's actual operator POST sequence is NOT
yet independently accepted as live HTTP end-to-end PASS. The underlying
staging engine's direct Docker lifecycle UAT did PASS.

This is NOT general arbitrary App Store parity. Other 725 catalogue
entries remain browse-only, and image upgrade, port mapping, secured app
proxy/web access, generalized multi-service setup and per-app rollback
remain unfinished. No app production cutover is authorized. The M1
release acceptance score stays 49/100 as last verified.
The user-disabled recurring progress monitor stays disabled.
