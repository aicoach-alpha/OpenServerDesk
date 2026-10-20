# Alpha 0.7.0-alpha.24 — Docker log timestamp compatibility

Real Dozzle UAT reached the staging-only SSE event list and displayed
verified container metrics, but its own log API returned HTTP 500 because
the synthetic broker rejected valid Docker time-window query formats.

The broker now accepts bounded Unix seconds/nanoseconds or validated RFC3339
(with up to nine fractional digits) on since/until. Empty/zero parameters
mean no time bound. Non-numeric, invalid calendar dates and arbitrary CLI
arguments remain forbidden. The source remains a verified immutable staging
container ID, 160-line limit, 64KiB maximum response and 5.5-second follow
window, with no unrestricted Docker API or Nextcloud user data access.

Four focused log tests PASS. Functional Dozzle UAT must still confirm that
the application's own log endpoint succeeds in staging.
No CasaOS production cutover is permitted.
