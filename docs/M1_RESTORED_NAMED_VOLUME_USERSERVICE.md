# M1 focused real UserService on restored Docker named volume — 2026-10-15

Ran the single focused gate in
`tools/staging/verify-restored-named-volume-user.py`.

- Installed the existing v0.3.0 candidate package contents in a disposable
  directory; used the actual packaged ReCasaOS UserService executable.
- Created only three unpredictable, labelled `osd-m1-fixture-*` Docker named
  volumes: source, backup and restored. Refused to reuse existing names.
- Temporarily stopped only `osd-m1-user` staging; production CasaOS remained
  untouched. The disposable real UserService joined the existing staging
  Gateway namespace and used the newly created source volume as its database.
- Synthetic registration and login against the source volume: PASS.
- Stopped the test UserService before backing up the named volume; copied
  backup into a *different*, newly created restored named volume.
- Started the real packaged UserService against **only the restored volume**;
  the identical synthetic credentials logged in successfully: PASS.
- Removed test container, restarted original staging UserService, removed
  all three uniquely named ownership-labelled volumes, and verified
  original UserService routed status: PASS.

Observed:
`SOURCE_NAMED_VOLUME_LOGIN_PASS`,
`RESTORED_NAMED_VOLUME_USERSERVICE_LOGIN_PASS`,
`OWNED_FIXTURE_VOLUMES_REMOVED_PASS`,
`ORIGINAL_STAGING_USER_ROUTE_RESTORED_PASS`.

This does not demonstrate entire CasaOS application/data migration,
multi-container application composition, production cutover, crash/power-loss
recovery, or security/pentest completion. Production migration remains blocked.
