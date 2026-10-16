# OpenServerDesk v0.6.27 native CasaOS App Store (STAGING ONLY)

16 October 2026, directly implemented and tested on andre-nas.

LIVE: Read-only browsing of the EXISTING CasaOS App Store cache at
/var/lib/casaos/appstore. Three sources contain 726 Compose definitions:
default 87; github.com 461; casaos.app 178. These are NOT unique app
families or installed app counts. CasaOS legacy x-casaos metadata is
parsed with yaml.safe_load without executing Compose definitions.

Authenticated staging dashboard supports searching the entire app store,
filtering 22 categories, choosing original store source, paged table
view, and per-app compatibility previews. Public data does not include
original Compose source file paths, user upload paths, env secret values,
or Docker mount sources.

GET /api/v1/stage/casaos-appstore provides read-only metadata.
GET /api/v1/stage/casaos-appstore?id=... provides compatibility
information only. An unauthenticated request is HTTP401.

Safety restrictions: source path strictly limited to the three existing
CasaOS platform store cache namespaces; symlinks never followed; YAML
input bounded in size and count; malformed and executable YAML tags
rejected. No images pulled, installations executed, containers touched,
logs fetched, app directories migrated or Nextcloud HDD accessed.

E2E: actual HTTP session authenticated with a stage reader, 726 records,
22 categories and a Nextcloud app preview. Existing 16 Docker container
identities remained unchanged after the test. 77 tests PASS from clean
Git source.

Package v0.6.27 SHA256:
2d8289048f8854586bb2a57e76f951b1e9eb7c568ae13cf60830d1292ed57904
Build source Git SHA: befa20071fa3d5a17999fa0ea38abce01ea78e07
Isolated staging service runs v0.6.27, detached STAGING Ed25519 signature
verified, rollback to v0.6.26 prepared, release receipt present, no
pending journal. Production CasaOS remains active in all six units.

NOT YET SUPPORTED: installing or updating arbitrary real CasaOS App
Store applications, privileged/host network apps, mount data migration,
or importing the new v2 remote index protocol. An isolated Docker
staging runtime and app-specific port, network, volume and rollback
safety acceptance are still required before enabling store install.
A functioning browse/search preview is NOT FULL CasaOS App Store parity.
No production cutover is authorized; migration_allowed=false.
The original M1 score of 49% is not automatically increased by browsing.
The user-disabled 15-minute automatic M1 monitoring remains disabled.
