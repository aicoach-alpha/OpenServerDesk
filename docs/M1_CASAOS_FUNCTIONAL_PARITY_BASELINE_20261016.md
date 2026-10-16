# M1 replacement parity requirements and real installed-app baseline

**Date:** 16 October 2026. **Rule:** 100% development acceptance must be
established in a non-production environment BEFORE any user-authorized
production activation. No production replacement, downtime, Docker
container mutation, or data upload migration during development.

The actual platform configuration at /var/lib/casaos/apps was inspected
via safe YAML parsing ONLY. No referenced bind paths, env files, Docker
volumes, or Nextcloud uploaded files were opened or copied.

## Actual incumbent workload compatibility baseline

- 18 valid Docker Compose app definitions (18/18 parsed).
- 19 defined services across those apps.
- 45 port declarations and 21 mount declarations (declarations, not
  distinct port numbers or filesystem byte counts).
- All 18 existing definitions require features outside the current tiny
  fixed-template staging manager. 0/18 app definitions have passed a
  GENERAL application import → service startup → persistence → restore
  end-to-end rehearsal. Two newly created safe demo templates have passed
  their separate staging tests; they DO NOT count as actual app parity.
- Most frequent missing source schema features include: container_name,
  cpu_shares, deploy, hostname, ports, environment, and CasaOS extensions.
  Full app configuration details and names remain in a private root-only
  report; the dashboard displays counts only.

Source and tests: tools/acceptance_m1_compose_compat.py;
tests/test_m1_compose_compat.py. Public bounded status:
GET /api/v1/m1/compose-parity. Private source metadata is not exposed.
The actual final release decision now explicitly blocks on the real
app compatibility gap, in addition to other release conditions.

## Minimum 100% development acceptance (separate from cutover authorization)

1. Verify full feature scope against real CasaOS v0.4.15 usage: dashboard,
   system metrics, original apps, Compose projects, app store/install/import,
   lifecycle, update policies, storage/file operations, users/authentication,
   backups/restore, network, logs, and system management.
2. Import ALL 18 legacy app Compose configurations into an isolated
   staging test deployment with unchanged functional semantics, including
   ports, environment and mounts translated safely to separately owned
   test resources; never mount original user data into test containers.
   Test actual workloads with independent, non-sensitive fixture data.
3. AppManagement and LocalStorage: authenticated create/read/update/remove,
   stop/start/restart, versioned update and downgrade, persistent state,
   quota control, error visibility and transactional recovery end-to-end.
4. Multi-user authentication and authorization: no shared universal stage
   operator token in production; per-user roles, isolated sessions, safe
   credential storage, CSRF and security tests.
5. Preserve every existing user-data bind and named volume reference
   without opening or copying Nextcloud uploads or changing filesystem
   ownership; validate mount reconstruction using controlled synthetic
   fixtures only.
6. Prove consistent cross-service platform state through an authorized
   isolated six-service upgrade and rollback, including kill/restart faults,
   database and metadata integrity, and explicit change journal recovery.
7. Demonstrate signed build provenance and independent code/security
   assessment plus scoped penetration testing; no false passing gates.
8. Complete full non-production E2E regression: package install, first
   login, app lifecycle, storage, backup/restore, rollback, browser UI,
   Docker compatibility, metrics and recovery.
9. The ONLY post-100 task is a separately authorized production migration
   during a maintenance window. Its readiness gate still requires user
   authorization. Do not conflate this permission with engineering
   readiness or make the original CasaOS services auto-stop.

**Current state**: Two fixed staged Compose templates and stage-only
rollback are LIVE in v0.6.18; v0.6.19 adds real incumbent Compose
compatibility coverage reporting. This is meaningful development, not
general CasaOS app parity. The historical M1 release acceptance score
remains 40%, based on other already accepted release gates. The 0/18
import figure is a SEPARATE compatibility measure, not percentage of
time remaining.
