# OpenServerDesk Alpha 0.7.0-alpha.29 — Dockpeek stage-only SECRET_KEY

## Implementation
- An actual Dockpeek staging install on Alpha .28 failed to start with
  RuntimeError: SECRET_KEY environment variable is not set (Gunicorn exit 3).
- The failed install was recovered using the existing stage lifecycle journal;
  the project was removed and two original staging projects remained.
- Generate an independent cryptographically random 64-character hex key at
  new Dockpeek project creation only, without inheriting any CasaOS production
  environment variables, settings, passwords or HDD data.
- The project-local key is persisted in a strictly validated UID1000-owned,
  mode 0600 non-symlink regular file within the stage root.
- Exactly one SECRET_KEY environment setting is permitted for the immutable
  Dockpeek image; every other environment or healthcheck is denied.
- The same stage key is retained during start, update, rollback, restore
  and project lifecycle; stage checkpoints never traverse host files.
- Refuse corrupted, unsafe, altered, cross-device or missing project key.
- Two focused secret lifecycle/security tests PASS.

## Boundaries
- Docker stage metadata facade remains read-only; no host Docker socket
  access or privileged mode. Dockpeek's actual UI/features require real UAT.
- Safe static plans remain 674/726; 52 source definitions need separate
  capability-specific host adapters.
- This release cannot replace CasaOS production.
- Origin 192.168.31.31:18691; https://osd.vervue.my.id
