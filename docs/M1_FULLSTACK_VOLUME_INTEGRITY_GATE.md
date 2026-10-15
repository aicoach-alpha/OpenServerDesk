# M1 full-stack restored-volume content integrity gate — 2026-10-15

Added `require_equal_volumes` to the existing focused full-stack
recovery runner. After quiesced source-to-backup copies and before
restored stack activation, isolated no-network BusyBox containers compare
the source and backup trees; similarly, backup and restored volumes
are compared after copying. All comparisons are read-only and fail
closed if any file contents or tree entries differ.

Focused staging test: actual packaged Gateway, MessageBus, and UserService
restarted using restored **synthetic** Docker named volumes, original
synthetic login and MessageBus subscription verified.
Observed `RESTORED_PACKAGED_THREE_SERVICE_STACK_AUTH_AND_BUS_PASS`,
`ISOLATED_STACK_AND_VOLUMES_CLEANED_PASS`.

Limitation: recursive diff tests logical file contents and tree entries,
not all metadata (ownership/xattrs/ACL), crash resilience, or real
application migration. Production CasaOS was not modified and production
migration remains locked.
