# M1 v0.4.31 to v0.4.30 database incompatibility — 2026-10-15

Real ReCasaOS UserService binaries were exercised on a disposable staging
database and isolated Gateway network namespace. On v0.4.31 a synthetic user
was registered and logged in successfully. The application was then stopped
and v0.4.30 was started against the **same post-upgrade database**, without
restoring a snapshot. Login with the identical synthetic credentials
returned HTTP 400 and application code 10013.

Observed result: cross-version authentication compatibility **fails** when
the older v0.4.30 binary reads credentials created by newer v0.4.31.
The standalone binary downgrade must not be considered a viable rollback.

Required release guard: preserve a verified, consistent pre-upgrade SQLite
snapshot and restore it together with the known-good binary; disclose that
writes created after the snapshot may be lost. Cross-version restoration
must be re-tested for each supported migration path. Do not enable
production migration based solely on synthetic evidence.

Test containers and ephemeral credentials were removed; original staged
UserService was restarted. No production data was used.
