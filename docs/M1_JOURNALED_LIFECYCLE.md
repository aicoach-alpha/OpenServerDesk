# M1 focused journaled pair lifecycle fixture — 2026-10-15

Executed tools/staging/verify-journaled-lifecycle.py on andre-nas.

It verifies two **real ReCasaOS UserService binary files** and a fresh
synthetic SQLite fixture, quiesces a constrained disposable container,
uses journaled_pair.replace_pair() to switch binary and database together,
validates restored SQLite contents and binary checksum, restarts the fixture
container, stops it, uses journaled_pair.recover() to undo the change,
checks original binary and DB contents, and starts the fixture again.

Observed: FOCUSED_JOURNALED_PAIR_LIFECYCLE_PASS.

Important scope: the disposable runtime is BusyBox with a read-only fixture
mount, NOT a live UserService process. This proves journaled file-pair
rollback synchronized with a container lifecycle, not UserService functional
rollback, version migration or atomic recovery across an unexpected power loss.
No production CasaOS file, service, application or volume was modified.
