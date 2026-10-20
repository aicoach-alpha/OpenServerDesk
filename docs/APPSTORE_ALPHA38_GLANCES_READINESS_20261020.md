# OpenServerDesk Alpha 0.7.0-alpha.38 — Glances startup gate fix

- Alpha .37 UAT found a concrete contract error: Glances install requested
  35 seconds while the stage readiness verifier enforces maximum 30 seconds.
  The install was automatically compensated; only the two original stage
  projects remained, with no pending recovery.
- The curated Glances stage install now requests 30 seconds, using the
  existing strict readiness boundary instead of expanding it.
- One focused mocked readiness check verifies 30 seconds is accepted and
  35 seconds remains rejected. No broad suite or repeated Docker audit.
- Exact image digest, stage-owned synthetic Docker socket, no host PID
  inheritance, isolated network and 256 MiB stage memory cap unchanged.
- The cached Glances image was prepared under the explicit staging-only
  Docker image cache workflow. Production containers, CasaOS services and
  Nextcloud external HDD were not touched.
- A single real UAT can now attempt install, HTTP readiness and uninstall.
