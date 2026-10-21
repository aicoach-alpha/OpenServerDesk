# OpenServerDesk 0.7.0-alpha.43 — reclaim verified empty staging on uninstall

## Implemented
- A successful isolated staging uninstall now completes the provenance-
  verified container/network removal, registry mutation and journal removal
  BEFORE attempting optional post-uninstall filesystem cleanup.
- For non-Qui applications only, reuse the existing strict stage-only
  validator to remove an empty generated Compose manifest, generated pilot
  secret and EMPTY stage volume/service directories if and only if there are
  no unexpected files, symlinks, mount points, registered projects, foreign
  network, Docker containers, recovery marker or nonempty application data.
- If cleanup fails safety validation, retain the directory and report
  empty_scaffold_reclaimed=false. Uninstall remains successful and original
  data retention stays guaranteed; there is no recursive deletion.
- Protected Qui application data is never automatically reclaimed.
- This release does NOT scan or delete historical unregistered directories.
  Read-only operator inspection and opt-in per-directory cleanup remain
  available separately.
- Three focused tests PASS: generated-empty cleanup, nonempty data retained,
  and foreign Docker/Qui project refusal, with no real Docker mutation.
- Earlier Alpha .40 Glances pilot was installed, internally served HTTP 200,
  and uninstalled in real staging UAT. Its browser feature parity still
  requires user acceptance.

## Safety
- No CasaOS production cutover, no host Docker daemon socket forwarded to
  third-party apps, no access to Nextcloud user data on external HDD.
