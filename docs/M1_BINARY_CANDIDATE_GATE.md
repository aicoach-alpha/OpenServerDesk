# M1 binary candidate fail-safe preflight — 2026-10-15

The staged ReCasaOS UserService known-good binary
`/opt/openserverdesk-dev/bin/CasaOS-UserService` was saved to an isolated
staging rollback directory. Its SHA256 was
`c3e8ddfda44c696f56c8577b09a5c50fc30022c4a29679d57c9902a75c16aafa`.

A deliberately invalid executable candidate terminated with expected exit
code 42. The source binary was verified byte-identical to the saved
known-good copy. Existing staged Gateway/UserService remained online, and
GET /v1/users/status succeeded. Six core units remained active.

This validates only **fail-safe preservation of a known-good binary** when
a candidate fails before replacement; it is not an upgrade or downgrade of
two real ReCasaOS builds, nor a running-service activation rollback test.

Required for a full gate: build/versioned candidate, activate only on
independent isolated staging, verify API and SQLite migration, deliberately
fail an activation, restore the previous build and database, and confirm
routing and MessageBus recovery. M1 migration readiness remains blocked.
