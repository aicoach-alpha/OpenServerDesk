# OpenServerDesk Alpha Workspace (20 October 2026)

Version 0.7.0-alpha.4. User-facing task-oriented redesign of the Alpha web
workspace, independently deployed alongside CasaOS production.

- Responsive sidebar navigation: Overview, Applications, App Store,
  Manage staging, Monitoring, and Release & migration.
- Overview shows live Docker counts, running containers, Compose projects,
  host memory, quick application preview and clear routing to Apps/Store.
- Apps Hub uses accessible cards, search, pagination and stage manager links.
- All previously registered DOM IDs and application callbacks are preserved.
  No backend Docker lifecycle behavior has been changed.
- Long, technical acceptance/migration checklists are visible ONLY on the
  Release & migration page; existing 49% milestone is not inflated.
- Raw Docker inventory remains read-only. Mutating stage actions still
  require the existing per-user authorization and target stage-owned apps.
- Alpha origin: http://192.168.31.31:18691 behind osd.vervue.my.id Cloudflare
  Tunnel and tailnet HTTPS. CasaOS production and Nextcloud user uploads
  must remain unchanged.

Verification: one HTML structure check, Node syntax check, Git integrity,
HTTP asset checks on Alpha and public origin; no repeated per-container UAT.
Full CasaOS feature parity, general production cutover, and broad browser
E2E acceptance remain OUTSTANDING, not PASS.
