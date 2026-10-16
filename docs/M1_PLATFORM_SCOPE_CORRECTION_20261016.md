# CasaOS replacement scope correction — 16 October 2026

User requirement: NEVER touch, move, copy, open, scan, hash, or modify
Nextcloud user-upload files on the external HDD. Existing Docker bind
mount paths and external user volumes must remain unchanged.

An earlier M1 estimate incorrectly included all Docker bind data, including
user uploads. The recommendation to provision 1–2 TiB extra storage is
WITHDRAWN. It is unrelated to replacement of the CasaOS dashboard.

New implementation: tools/migration/m1_platform_scope.py. It obtains
container paths and Compose project files only through Docker Engine
metadata. It selects existing platform configuration directories
/etc/casaos, /var/lib/casaos, /etc/docker where present, and selected
existing Compose YAML definitions under safe platform prefixes.
Docker image layers, volumes, application upload trees, external HDD
content and Nextcloud user files are NOT part of the migration backup.

Protected source boundaries: /mnt/data, /media, /run/media,
/srv/nextcloud/data, /var/lib/nextcloud/data, unknown other /mnt mounts,
and recognizable Nextcloud data/uploads/files segments. Lexical
exclusion is performed before filesystem lookup, so no user file data or
metadata needs to be read. Nested mounted filesystems and external symlinks
inside approved configuration trees require fail-closed review.

Verified from Docker metadata (without reading user HDD content):
* 16 container references, 10 Compose project labels.
* 13 selected platform configuration roots/files.
* 4 bind references filtered as protected.
* No user files copied, opened, inspected or changed.

A separate device was seen for the SSD vs selected platform config
filesystem. This does NOT establish actual backup sufficiency, user-data
copy need, nor permit a production cutover. Scoped config backup/recovery,
AppManagement compatibility, cutover rollback and final security signoff
still require authentic acceptance evidence.

Production untouched. migration_allowed=false. No requirement to copy
Nextcloud user uploads or replace/migrate its external HDD.
