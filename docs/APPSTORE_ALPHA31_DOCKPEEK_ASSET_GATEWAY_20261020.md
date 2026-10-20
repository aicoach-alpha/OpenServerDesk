# Alpha 0.7.0-alpha.31 — Dockpeek browser assets through staging gateway

- Real Dockpeek v1.7.2 image now installs in an isolated stage project
  with per-project SECRET_KEY and DISABLE_AUTH, only behind the authenticated
  OpenServerDesk stage-app gateway.
- Real stage-owned Dockpeek HTTP root and /health both responded 200.
  The original HTML uses root-relative CSS/JS paths under /static.
- Gateway rewrite now includes root-relative /static/, /export/ and /logout
  within the exact authenticated /stage-app/<project>/ namespace.
  Existing /api/ and /assets/ rewriting remains unchanged.
- Two targeted assertions PASS: HTML URLs scoped to the exact project and
  JSON payloads unchanged; no broad Docker/container test suite repeated.
- Stage authorization, only verified internal network endpoint, no
  original Docker socket, no Nextcloud external HDD files and no CasaOS
  production mutation are unchanged.
- The browser itself still requires owner UAT; static rewrite tests alone
  do not prove every Dockpeek feature, image, or websocket works.
- Other restricted catalog applications and production cutover remain out
  of scope. CasaOS production stays active.
