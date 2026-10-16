# CasaOS real application compatibility — semantic analysis (16 Oct 2026)

This is an incremental static compatibility discovery feature, NOT imported
application execution, parity acceptance or production cutover.

The new tools/compose_semantics.py reads only CasaOS-controlled app
Compose YAML definitions via the already strict config reader, and NEVER
reads referenced bind paths, HDD user uploads, .env contents or application
data. It reports generic Compose feature names and counts only; it deliberately
does not echo service names, paths, ports, environment keys or values.

At time of first execution:
- 18 actual platform Compose definitions analyzed; runtime-import parity 0/18.
- 0 declared Compose internal dependency edges among those definitions.
- 11 application service uses of environment, 19 network_mode,
  17 ports, and 17 volumes detected as restricted for safe isolated
  fixture replay (counts are occurrences, not distinct applications).
- Two uses of shm_size and six x-casaos extension fields require
  explicit schema support or deliberate compatibility handling.
- The parser rejects invalid dependency references, unexpected structures,
  and redacts credential and path values before producing its report.
- Four synthetic unit tests PASS including private string non-disclosure,
  unknown field classification, cyclic self-dependency and absent
  service reference rejection.

This creates a precise roadmap for implementing a capable stage-only
Compose adapter without risking accidental use of real production mount
paths. It does NOT increase 40% accepted end-to-end release milestones
until authentic application import/start/persistence/recovery are verified.

Production CasaOS is intact, user data HDD must remain untouched, and
migration_allowed=false.
