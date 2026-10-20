# OpenServerDesk Alpha 0.7.0-alpha.11

## Implemented
- The local CasaOS App Store includes 726 indexed entries.
- 670 entries have sandbox-only plans; 53 require privileged host interfaces
  and remain gated; 3 metadata declarations remain incompatible.
- Genuine Compose one-shot init dependencies retain the original
  service_completed_successfully condition.
- Compiler and runtime reject conflicting dependency conditions.
- Readiness checks that init jobs exit with code zero; nonzero jobs fail.
- Lifecycle status distinguishes physically running services and completed
  init jobs, without weakening health check validations.
- Backup/restart, start, stop, update, rollback and data recovery remain
  owner-scoped staging lifecycle controls.
- Plan preview names one-shot initialization services.
- Four targeted tests cover real Buzz, Ente, OpenClaw metadata, dependency
  completion exit codes and conflict rejection.

## Deployment and boundaries
- 670 means sandbox planning only, not application functional equivalence.
- Host Docker socket, system files, external hardware and original CasaOS
  production data are not imported or enabled.
- No production cutover, Nextcloud HDD access or CasaOS service replacement.
- Alpha origin: 192.168.31.31:18691; URL: https://osd.vervue.my.id/.
