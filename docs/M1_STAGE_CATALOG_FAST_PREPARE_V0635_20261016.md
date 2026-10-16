# OpenServerDesk v0.6.35 - CasaOS store catalogue performance + multi-service preparation

## Runtime and security scope
- This is staging-only. CasaOS production services remain running.
- No Nextcloud user uploads or external HDD paths are inspected.
- Catalogue indexing uses the existing CasaOS platform appstore metadata under /var/lib/casaos/appstore only.
- Private metadata path mapping is never returned through the catalogue API.
- Cached paths are checked for symlinks and inode/size/time changes before reading.
- YAML parsing uses LibYAML CSafeLoader, falling back to SafeLoader without allowing arbitrary Python objects.
- Multi-service image preparation requires an authorized write operation and is explicit in the UI.
- Preparation downloads only image references from existing catalogue definitions into Docker's image cache; it never starts applications, accesses original bind mounts, or changes running production containers.
- Disk free space gate and post-pull per-image size and immutable ID checks are enforced.

## Local measurements (read-only)
- Real platform catalogue: 726 application definitions.
- Cold parse before optimization: 17.048 s.
- Cold parse after CSafeLoader: 2.365 s.
- Indexed selected-app lookup: 0.31 ms after cache is loaded.
- MySpeed compiler preview after cache warm-up: ~0.10-0.14 s.
- These are measured example runs, not guaranteed latency SLAs.

## Still NOT accepted
- Functional browser access to actual installed catalogued applications remains unverified.
- Multi-service API install/update/rollback real Docker UAT was not permitted during previous run.
- Application data/database consistent rollback and crash-recovery E2E remain unverified.
- Password/env integration, health checks, production-equivalent cutover, and general catalogue parity remain incomplete.
- Progress remains 49%, migration_allowed=false. No automatic monitoring is restarted.
