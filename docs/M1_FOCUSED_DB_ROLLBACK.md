# M1 focused staged SQLite rollback with authentication verification — 2026-10-15

Test scope: isolated UserService fixture database only. The original
ReCasaOS staged UserService container was temporarily stopped and later
restored. No CasaOS production data or services were changed.

1. Started the actual staged ReCasaOS UserService binary against a fresh
   fixture database and created an ephemeral synthetic account: login PASS.
2. With the disposable UserService container stopped, created a verified
   SQLite snapshot using the existing snapshot helper.
3. Changed the synthetic database by deleting the sole account from
   its actual `o_users` table.
4. Restarted the disposable service; the synthetic login was rejected.
5. Stopped it, restored the pre-mutation SQLite snapshot, and restarted.
6. Identical synthetic credentials successfully logged in after restore.
7. Removed the disposable container and fixture, restored the original staged
   UserService, and confirmed its routed user status responded correctly.
8. Six CasaOS/Docker/OpenServerDesk systemd units remained active.

**PASS:** scoped manual database rollback and functional authentication
recovery with a real UserService binary and isolated synthetic DB.

**Not PASS:** automatic journal-based service rollback, persistent volume
recovery, in-place CasaOS replacement, power-loss recovery, or M1 pentest.
