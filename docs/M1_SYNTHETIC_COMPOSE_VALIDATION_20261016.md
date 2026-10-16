# Staging-only Compose structural validation against 18 real CasaOS definitions

Tool: tools/synthetic_compose_rehearsal.py
Tests: tests/test_synthetic_compose_rehearsal.py

Reads ONLY the CasaOS-controlled docker-compose.yml configuration definitions
(not user files or mounted content). Converts their service topology into
entirely synthetic BusyBox-only, network-isolated Compose fixtures, dropping
ALL real images, commands, environment, credentials, published ports,
volume/bind declarations, capabilities, and other production behavior.
The synthetic files are generated within an ephemeral staging directory.
Only docker compose config --quiet is run, with NO containers started,
no images pulled and no production modifications.

Verified 16 Oct 2026:
18/18 real installed Compose configurations accepted as structurally valid
synthetic configurations, representing 19 synthetic service declarations.
No original real-world application has been imported, booted, or verified;
general application functional parity stays 0/18 E2E and production
replacement continues to be blocked. Synthetic validation must NEVER count
as production parity, security clearance or M1 100% acceptance.

Automated tests cover non-disclosure of credentials, port values, host mount
paths and image references, plus invalid service key rejection.
Nextcloud upload contents on the external HDD are excluded and untouched.
