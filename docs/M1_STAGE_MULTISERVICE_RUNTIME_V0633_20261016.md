# OpenServerDesk v0.6.33 – isolated multi-service runtime, 16 Oct 2026

STAGING IMPLEMENTATION ONLY. Not CasaOS production parity.

New executable runtime: server/stage_store_runtime.py

Implemented:
- Install an isolated Compose project compiled from CasaOS catalog
  definitions only if every image is present as immutable Docker sha256.
- Each new project has an osd-compiled random-hex identity.
- No network, no host port publishing, no production bind paths,
  no original env or privileged configuration, stage-only storage.
- Dedicated ownership labels, full Docker container ID verification,
  immutable image identity, and project-scoped lifecycle.
- Start, stop, restart and uninstall verified staged containers.
- Image/config updates journal previous configuration before replacement.
- Revert image/config to previous revision while retaining stage volumes.
- Recovery logic for interrupted operations exists but crash recovery
  UAT has NOT passed and is not accepted.

REAL Docker UAT for two isolated staging services:
- Install BusyBox two services PASS.
- Stop and start PASS.
- Update both images from BusyBox to Alpine PASS.
- Image and configuration rollback PASS.
- Uninstall PASS.
- All 16 preexisting Docker container IDs remained unchanged.
- Four additional focused boundary tests PASS.
- Database transactions/data-volume contents were not rolled back.

Release:
- Built from clean Git SHA 2b7243771f86a734e9c23489cff6553ff8845052.
- Candidate v0.6.33 SHA256:
  3b1bf8a9bc414b737a11c45caac2d3c2a324933ee066326649ea6b3f1a47765e
- Local staging Ed25519 signature verified.
- Active isolated staging service runs packaged v0.6.33, with rollback
  to v0.6.32 on failed release checks.
- Runtime module present in actual staging release.
- All six original CasaOS production services remain active.

Important limitations, NOT PASS:
- The user-facing authenticated compiled-runtime API change was
  blocked by the execution environment's safety controls and was not
  activated. Browser and API lifecycle UAT cannot be claimed.
- Crash recovery remains unverified.
- Real multi-service catalog apps needing network will not function
  fully with network-none staging isolation.
- Application database/data volume rollback is not implemented.
- General CasaOS App Store parity and production acceptance incomplete.
- CasaOS production never replaced, no user Nextcloud uploads copied,
  moved, inspected, migrated or opened.
- Last accepted M1 milestone progress remains 49%.
- User-disabled automatic monitoring remains disabled.
