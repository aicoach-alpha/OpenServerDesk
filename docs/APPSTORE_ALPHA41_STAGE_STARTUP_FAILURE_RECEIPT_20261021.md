# OpenServerDesk Alpha 0.7.0-alpha.41 — safe startup-failure receipt

## Implementation
- Capture the last failed stage startup as a private, root-stage-scoped JSON
  record (0600), after verifying exact stage project/container provenance.
- Include only catalog app ID, random stage project ID, sanitized error code,
  bounded service statuses, exit codes and a very small set of recognized
  fault categories such as the missing nonroot UID/passwd entry encountered
  by Glances. Never persist Docker stdout/stderr, tracebacks, credentials,
  environment values, source paths or application data.
- Record whether the failed installation was successfully rolled back,
  requires recovery, or remains under the existing Qui owner review process.
- Read-only operator App Store listing exposes at most the latest bounded
  receipt, with a dedicated textContent-only status line. No public or
  unauthenticated endpoint is added.
- The evidence workflow is best-effort: diagnostics can NEVER block rollback,
  replace the actual AppError, or inhibit removal of a verified empty stage
  scaffold following compensation.
- Three focused receipt/security tests plus two focused existing failed
  startup compensation tests PASS. Only syntax/compile sanity checks otherwise.

## Actual Glances result
- Alpha 0.7.0-alpha.40 fixed the Glances crash caused by upstream
  getpass.getuser() querying an absent passwd entry for sandbox UID1000.
- One real Glances stage installation returned running=true; the verified
  internal web endpoint returned HTTP 200 with HTML. Its temporary project
  was uninstalled successfully; the two original stage projects and zero
  pending recovery markers remained. Browser UI and all monitoring features
  are NOT proven by this success.

## Platform boundaries
- CasaOS production remains untouched and authoritative (no cutover).
- Nextcloud user data on the external HDD is never inspected or migrated.
- Image/plan support: 675 of 726 definitions can compile to isolated sandbox
  plans, not proof of full application feature parity.
