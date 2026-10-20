# OpenServerDesk Alpha 0.7.0-alpha.30 — Dockpeek staged gateway login

## Implemented
- Dockpeek runtime needs SECRET_KEY and requires its own USERNAME/PASSWORD
  unless DISABLE_AUTH is enabled. Alpha .29 supplied a per-project random
  secret, but the image still exited at startup. Failed stage fixture was
  recovered by the existing install journal; two original projects remained.
- Only the curated, exact-digest Dockpeek staging pilot now receives
  DISABLE_AUTH=true and the same random, stage-project-owned SECRET_KEY.
- The app must remain on the isolated Docker network, use a loopback-only
  Docker port and be accessed through authenticated OpenServerDesk stage
  gateway. This is NOT general permission to disable auth for CasaOS apps.
- No host Docker daemon socket, external HDD data, production credentials,
  arbitrary container permissions or remote public Dockpeek binding.
- Dockpeek credential and auth-mode test passed.
- One real isolated install/access/uninstall is required to verify runtime
  behavior; safe App Store static coverage remains 674/726.
- CasaOS production cannot be replaced at this Alpha release.
