# M1 initial security review — 2026-10-15

A targeted fixture path audit found a trust-boundary weakness:
`volume_fixture.snapshot()` resolved the root before checking symlink
status, causing a symlinked input root to be treated as an ordinary path.

Fixed by rejecting a symlink root BEFORE canonicalization. Regression test
proves the root alias is rejected. Full Python suite: 35 PASS.

This is an initial issue-driven security review, **not a complete pentest**.
Remaining requirements include path traversal and manifest adversarial cases,
external volume/Compose recovery, service quiescence and permissions,
journal crash-consistency under actual forced restarts, signed package supply
chain checks, and independent security gate. The migration API remains blocked.
