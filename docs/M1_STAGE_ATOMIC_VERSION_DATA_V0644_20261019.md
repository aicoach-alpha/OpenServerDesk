# OpenServerDesk 0.6.44 — staging-owned version/configuration and data consistency

This release changes compiled staging App Store update/rollback from configuration-only to a quiesced cold-stage-data transaction.

- No-op updates do nothing. Real version changes journal the exact original/target manifest, revision, state of previously running stage services and prior rollback references before stopping any container.
- Stop only verified stage-owned containers, then create a content-SHA256 and SQLite quick-check-backed checkpoint, durably pinned in the recovery journal *before* rewriting Compose or restoring old data.
- Update starts the new target and observes readiness. Its durable previous.json and previous-data.json pair link the previous image configuration to its exact preserved data checkpoint.
- Rollback requires a validated previous manifest and matching previous-data.json checkpoint, restores previous data only while stage containers are stopped, activates the linked configuration and verifies readiness. A successful rollback saves an inverse checkpoint so a later rollback can reverse it again.
- On a failed version change, automatically restore original configuration and exact pre-operation data, but only if every existing project container passes strict current/old immutable image and Docker provenance checks. If any ambiguity arises, retain the journal and block further changes pending explicit recovery.
- The existing recovery operation accepts the version-2 change journal and restores original config/data. Old version-1 journals are still supported as configuration-only legacy recovery and cannot be claimed data-safe.
- A previous-data checkpoint referenced for rollback cannot be manually deleted until a new version transition replaces the link.
- All mounts are isolated stage-owned paths. No CasaOS production services, production Compose projects or external Nextcloud uploads are modified.
- Real *changed-image* staging deployment remains to be verified with a suitable cached candidate; no fake cross-image parity claim. This is not a production cutover approval.

## Authentic staging UAT — 19 Oct 2026
- Signed v0.6.44 artifact deployed LIVE to isolated staging; production_modified=false, migration_allowed=false.
- With MySpeed running, applied a reversible Compose-only metadata revision (an empty depends_on list). Image SHA, Docker network and staging bind volumes were unchanged. This exercises a real configuration change, NOT an image version upgrade.
- The update transaction quiesced MySpeed, recorded exact pre-change volume snapshot data-1866f2d80945, activated revision 2 and returned HTTP 200.
- Actual rollback of revision 2 restored linked database snapshot and original Compose manifest; revised runtime reports revision 3 with application_data_rollback=true. MySpeed HTTP returned 200 after rollback; transaction/recovery journals were absent.
- The disposable data-1866f2d80945 snapshot was safely deleted after the rollback. The operator baseline data-daf626140840 and the current rollback-pinned data-46b061f7b45f remained; MySpeed remained HTTP 200.
- Four focused v0.6.44 unit tests PASS. Full image replacement, image rollback, multi-service data-consistency, load testing, and general CasaOS parity were not claimed or tested.
- All operations were limited to OpenServerDesk compiled staging project. Production CasaOS and Nextcloud user volumes were not migrated or modified.
