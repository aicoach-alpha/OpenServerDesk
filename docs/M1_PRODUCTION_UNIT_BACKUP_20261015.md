# Live original CasaOS systemd service configuration preservation

At 19:07 WIB 15 Oct 2026, with six live CasaOS services confirmed
active, the exact six original systemd service definitions were captured
to root-private storage without a single production service restart.

Tool: tools/migration/m1_service_unit_backup.py
Backup location: /var/backups/openserverdesk-migration/
Snapshot ID: casaos-units-20261015T120716Z
Manifest SHA256: 043b70d8fceb1e2c80cb1739e04dd508c144ca21e22b811564a466b89f924bb6

The tool checks the exact six service file and drop-in paths resolved
through systemd, preserves owner, group, modes and content SHA256 in
a durable manifest, and publishes the snapshot atomically.

Validation explicitly restores all unit files into a disposable,
isolated staging directory and compares hashes. The tool does NOT
copy them back over /etc/systemd or replace live systemd units.

This complements the real CasaOS config+three SQLite online backup
recorded at 18:31 WIB in the same backup root. These two backups
do NOT prove complete app data protection: 16 running Docker
containers with 40 Compose/bind source paths remain active. Full
maintenance quiescence and independent restore still mandatory.

Use this backup as an input to a future *explicitly authorized*
production cutover rollback controller, not as proof FULL PASS.
