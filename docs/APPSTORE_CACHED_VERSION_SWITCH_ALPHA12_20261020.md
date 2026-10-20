# OpenServerDesk 0.7.0-alpha.12 — staged image-version switching

## Implemented
- Authorized stage operators may choose a cached image tag only for their
  already-owned SINGLE-service CasaOS App Store application.
- Target repository is derived from its original locally cached CasaOS
  catalog metadata, not from user-controlled URLs.
- Input accepts strictly a valid tag only; digest-pinned catalog sources,
  other repositories, untrusted references and uncached images are refused.
- Stage inventory lists up to 32 cached same-repository tags for eligible
  projects, without downloading or building anything.
- Advanced lifecycle panel offers a version selector and Switch cached version.
- The version change uses existing durable stage-only update journal,
  pre-update cold data snapshot, container provenance verification,
  immutable image ID, restart readiness and exact rollback-linked checkpoint.
- A normal no-change update remains a no-change result.
- Previous app data and CasaOS production containers are never imported.
- Four focused tests validate repository scope, bad tags, immutable ID
  pinning, cache rejection and non-version operations.
- The App Store plan remains 670/726; 53 privileged host integrations and
  three incompatible source metadata entries remain marked blocked.

## Acceptance
- User-facing Switch Version must not be considered a successful upgrade
  until an isolated image-version transition and image+data rollback pass
  a real staging E2E fixture.
- Production cutover is NOT authorized, CasaOS remains the production panel.
- Nextcloud user HDD data and existing production Docker workloads untouched.
- Public Alpha: https://osd.vervue.my.id ; LAN origin 192.168.31.31:18691.
