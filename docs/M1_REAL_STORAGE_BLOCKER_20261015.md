# M1 external recovery storage — 15 October 2026, read-only

Direct SentinelX inspection of real Docker source paths and NAS filesystems:
- 40 unique backup sources: 30 Docker bind paths + 10 Compose files.
- 16 Docker containers active and 25 writable mounts.
- All three NAS filesystems contain application/Compose source data:
  root volume 27 source paths, SSD 10, HDD 3.
- Source data measured on HDD (/mnt/data) approximately 977.83 GiB;
  all 3 HDD paths responded. Other source data includes at least 7.54 GiB
  on the SSD with one unmeasured path; complete backup size remains UNKNOWN
  until all sources are measured.
- Available space: root 23.57 GiB, SSD 32.53 GiB, HDD 724.63 GiB.
- These are the SOURCE disks, not independent off-host backup devices.
  The HDD alone contains more source bytes than free space on the HDD.
- The m1_storage_safety_gate.py preflight confirmed no independent mounted
  backup target; it refuses to mark an existing data disk as independent.
- The production release decision now has an explicit
  independent_backup_destination blocker in addition to original gates.

**Required before ANY production maintenance:** provide a separate physical
disk, NAS destination or remote backup store with enough free capacity.
Provisional minimum is more than 1 TiB for just one full copy. For a complete
separate full-restore rehearsal while retaining the original verified backup,
allow around 2 TiB or more independent free capacity, subject to completing
size measurements and filesystem metadata assessment. Remote filesystems
require separate integrity and recovery validation; a file on the original
disk is not an independent backup.

Do not stop applications, overwrite paths or claim M1 production readiness.
This is an inspection and policy gate only: production_modified=false and
migration_allowed=false. Real cutover requires operator-approved maintenance
and final independent security acceptance after a verified external backup.
