# Alpha 0.7.0-alpha.23 — Stage broker load and reconnection

Changes: serialize staging container provenance refresh with 3-second TTL;
keep failed identity refresh fail-closed; allow four bounded Docker stats
readers and 16 total broker client threads; event sessions capped at 38
seconds and stats sessions at 25 seconds. Service limits remain CPU 60%,
RAM 160MiB, 48 tasks. A systemd-owned Unix socket keeps its inode across
broker restarts. No unbounded host Docker API, filesystem access, user
Nextcloud data, or CasaOS production container mutation is authorized.

Three focused cache/slot tests PASS. A real Dozzle UAT found repeated event
EOF and overload during refresh under Alpha 0.7.0-alpha.22; this update is
intended to fix capacity. Dozzle UI log rendering is NOT declared PASS until
runtime evidence is captured. Static sandbox plans remain 673/726, with
53 host-capability cases limited. No CasaOS production cutover.
