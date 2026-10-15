# M1 incomplete undo journal preparation gate — 2026-10-15

The fixture-only recovery prototype prepares its undo journal under
`.osd-undo-preparing`, fsyncs copies and the manifest, then renames the
completed directory to `.osd-undo` before changing either target file.

An abrupt subprocess exit is injected after the first undo-file copy.
Test evidence verifies both target files are unchanged, and further
replace/recover calls refuse to proceed when an incomplete preparation
directory exists. All Python tests: **27 PASS**.

This is fail-closed, not automatic recovery of an interrupted preparation.
Operator-controlled cleanup or stronger journal state handling is still
necessary. There is no process lock, live DB quiescence, disk-full handling,
power-loss test, or durability certification. Production migration remains
blocked until the wider rollback and security gates pass.
