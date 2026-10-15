# M1 focused real UserService journaled rollback — 2026-10-15

One focused staged test using actual ReCasaOS UserService executables and a
disposable synthetic SQLite database, with the original staged UserService
temporarily stopped. A first attempt discovered that the journal copy helper
did not preserve execute permission on binary replacements; this was corrected
by preserving mode bits on copied files.

The rerun demonstrated:
- Real v0.4.30 UserService synthetic registration and login: PASS.
- Journaled binary/DB replacement to real v0.4.31: PASS.
- Real v0.4.31 UserService synthetic login: PASS.
- Journaled undo to original v0.4.30 binary and database: PASS.
- Real v0.4.30 UserService original synthetic login: PASS.
- Removal of disposable fixture/container and restoration of original
  staging UserService: PASS.
- Six production/staging systemd units active after completion.

Scope: integrated controlled staging service stop/start with journaled
binary/SQLite replacement and undo. Does not prove power-loss atomicity,
real host migration, persistent app volume recovery or M1 pentest.
Migration readiness remains blocked pending wider required gates.
