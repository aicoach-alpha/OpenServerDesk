# OpenServerDesk 0.7.0-alpha.33 — pre-install staging cleanup

## Delivered
- Auto-compensate failures during new stage preparation BEFORE Docker
  Compose has created any containers: catalog compilation, project-local
  secret generation, network/port selection, volume preparation, generated
  manifest verification and install journal preparation.
- Cleanup acts exclusively on a newly generated osd-compiled project
  directory, owned by the current non-root andre user and located on the
  approved isolated stage filesystem.
- Preflight rejects a registered project, recovery journal, symbolic link,
  mount point, unexpected files, non-empty volumes, foreign inode ownership,
  and any Docker container/network using the project namespace.
- Only approved generated files (stage manifest, Qui or Dockpeek stage
  secrets) and EMPTY newly created stage volume directories can be removed.
  No recursive removal or traversal of user data is permitted.
- When cleanup is unsafe, retain all evidence, report an explicit
  compiled_stage_prepare_cleanup_required error and leave production
  untouched. The UI differentiates this from safely cleaned preparation.
- Existing auto-compensation AFTER Docker startup, protected Qui slow-start
  finalization, registry provenance checks and stage data-retention rules
  remain intact.

## Targeted verification
- Four focused isolated tempdir fault-injection tests:
  compile error clears generated secret, failed empty stage volume is
  removed, unexpected user data survives, and unexpected Docker project
  namespace prohibits cleanup. No real production or staging Docker
  containers are altered by the tests.
- Python compile and JavaScript syntax checks; a single post-deploy
  health/registry/CasaOS integrity check.

## No cutover
- CasaOS production stays authoritative. Existing registered staging
  projects are not removed.
- No Nextcloud user data, external HDD, CasaOS volume, or original host
  Docker project is touched.
