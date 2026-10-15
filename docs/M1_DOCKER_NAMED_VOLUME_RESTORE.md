# M1 focused actual Docker named-volume restore — 2026-10-15

Executed `tools/staging/verify-docker-named-volume-restore.py` directly on
the staging host. This is one isolated Docker named-volume gate.

- Three cryptographically random `osd-m1-fixture-*` volumes were created
  for source, offline backup, and restored destination; the script refuses
  pre-existing names and verifies a fixture ownership label.
- Constrained disposable BusyBox containers used `--network none`, a
  read-only root filesystem, dropped capabilities, and no host port bindings.
  No existing CasaOS or user Docker volume was mounted.
- An application configuration file, another persistent state file, and an
  intentional file mode (0640) were written to the source.
- After writers exited, a file-tree backup was copied to the backup named
  volume; the original source was modified and one file deleted.
- Restored into a **new Docker named volume** from the backup. Checks
  verified original file contents, file mode, restored deleted file, absence
  of post-backup files, and unchanged mutated source. PASS.
- Only the three generated, label-verified fixture volumes were removed;
  none remain. PASS.
- All six production/staging systemd units active; all three original
  ReCasaOS staging containers remain running.

Limitations: not an online/concurrent-writer backup, production named-volume
migration, Docker Compose relinking, permission/xattr/UID fidelity across
different hosts, or atomic power-loss restore. The new restored volume was
verified as a volume but not attached to a full restored application stack.
M1 readiness remains blocked pending full-service restoration and final
security audit/pentest.
