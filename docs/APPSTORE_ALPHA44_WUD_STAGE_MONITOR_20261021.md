# OpenServerDesk Alpha .44 — Whats Up Docker curated stage monitor pilot

- Implements exact digest-pinned WUD 6.6.1 from the existing CasaOS
  catalogue in the compiled isolated stage-only App Store. The one
  approved source service is app, with one docker socket volume and
  the published web application port 3000. Any extra privilege, device,
  host namespace, changed image, environment or network setting is denied.
- WUD receives the synthetic stage-only read-only Docker API socket,
  never the real Docker daemon socket. UID 1000:1000, all capabilities
  dropped, no-new-privileges, 256 MiB memory limit and internal-only
  stage network remain enforced in the existing compiler/runtime.
- This intentionally permits inventory/monitoring of isolated stage
  containers only. External registry access/update scanning is NOT
  available, and no production containers, secrets, host volumes or
  external Nextcloud user HDD are exposed.
- Three focused exact catalogue, compiler and feature-gap assertions PASS.
- Safe stage plans: 676/726; remaining 50 host-limited.
- A real one-off stage install, internal HTTP and uninstall UAT is required
  after Alpha .44 deployment before reporting WUD runtime compatibility.
- No CasaOS production cutover; .43 failed-uninstall scaffold cleanup
  remains part of the release with no change.
