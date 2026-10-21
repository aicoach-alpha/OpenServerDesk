# OpenServerDesk Alpha 0.7.0-alpha.42 — bounded failure diagnosis

- The private stage startup receipt introduced in Alpha .41 can classify
  known failure reasons without persisting or returning raw Docker logs.
- The diagnostic reader now consumes at most 8192 bytes total from
  stdout/stderr, using a fixed 24-line Docker logs request for a verified
  exact stage-owned 64-hex container ID. No shell or user-chosen path.
- Each reader expires in 3 seconds; only up to 3 exited stage services
  are inspected per failed installation, while service exit-code metadata
  may still cover up to the approved 12-service compose plan.
- Untrusted oversized container logs cannot fill the Python process's
  memory via unbounded subprocess capture_output.
- If the reader is unavailable, the receipt falls back to unclassified,
  and rollback/cleanup remain the authoritative lifecycle operation.
- Only allowlisted error fingerprints and exit/status codes can be stored
  in the permission-0600 last-failure record under the staging-owned root.
- Five focused receipt/security tests PASS (two bounded stream and three
  provenance/metadata tests). No repeated Docker integration audit.
- The cached Glances web application has already passed one real staging
  install, HTTP 200 root, and uninstall in Alpha .40. Glances web browser
  feature parity remains unproven; its bundled UI uses relative
  static/glances.js and api/4/... paths, which align with stage gateway.
- CasaOS production remains live; no cutover, no Nextcloud external user
  HDD data access, no host daemon socket exposure to staging apps.
