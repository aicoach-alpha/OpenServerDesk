# v0.6.20 LIVE CasaOS replacement host monitoring (staging only)

Released and tested directly on andre-nas 16 October 2026.
Dashboard and GET /api/v1/system/status present real NAS data:
logical CPU core count, 1/5/15 minute load, MemTotal/MemAvailable/swap,
uptime from /proc/uptime, and filesystem use only for '/' and
'/mnt/ssd-turbo'. The read-only endpoint contains no user file names,
external HDD mount contents, network secrets or Docker credentials.
No statistics or filesystem metadata from /mnt/data were requested.
The server source explicitly allowlists only two filesystem roots.
A negative unit test proves attempts to request /mnt/data are rejected.

The v0.6.20 package was SHA-checked and activated only on the isolated
OpenServerDesk staging service through version-pinned journaled
0.6.19 -> 0.6.20 upgrade with automatic rollback to 0.6.19 when its
health checks fail. Tested HTTP200 /health, /ui, /api/v1/system/status,
Docker read-only inventory, Composer compatibility baseline and cutover
plan. Authenticated stage Compose lifecycle and checkpoint rollback
were re-tested on real Docker Engine; all 16 existing container IDs
and all six production CasaOS services remained unchanged.

Artifact SHA256:
99d6b8066b01d354784f182bbc77f169f82f54ccc026fa02c950b648da1bed79

This addresses ONE important incumbent dashboard feature but does
NOT prove full functional parity. 18 CasaOS application definitions
remain unverified for general import/lifecycle. Production cutover
and any migration continue to be forbidden without separately
verifiable full development acceptance and explicit user authorization.
