# M1 ReCasaOS UserService restart recovery — 2026-10-15

Physical test on isolated staging, no production changes:

1. Confirmed staging Gateway Docker network mode is `none`, with isolated UserService config and database mounts.
2. Checked baseline Gateway /ping and /v1/users/status: responding and initialized.
3. Recorded checksums for one staged UserService SQLite database.
4. Stopped and restarted **the actual staged ReCasaOS UserService** container.
5. Checked UserService container running; database checksums identical.
6. Rechecked /v1/users/status through the real staged Gateway: initialized.
7. Confirmed UserService log reports successful Message Bus websocket subscription after restart.
8. Verified CasaOS, CasaOS-Gateway, CasaOS-UserService, CasaOS-MessageBus, Docker and OpenServerDesk staging units all remain active.

**PASS**: UserService staging service restart, data persistence and route/event reconnection.
**NOT PASS**: binary version upgrade/downgrade, rollback of schema migrations, full container stack recovery, real CasaOS migration or M1 pentest.
