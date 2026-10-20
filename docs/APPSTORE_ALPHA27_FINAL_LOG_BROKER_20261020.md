# OpenServerDesk Alpha 0.7.0-alpha.27 — permanent Dozzle log acceptance

- Immutable release built after reconciling concurrent source commits.
- Accept validated Go zero-time negative fractional Unix log timestamp as
  an unbounded lower/upper query end; invalid user inputs remain rejected.
- Removed temporary diagnostic code and transient systemd override.
- Preserved prior long-lived, bounded event and metrics readers, stage-only
  provenance cache, stable systemd-owned Unix socket inode and API write deny.
- Real staged Dozzle log backend: HTTP 200, 6,346-byte sample. The UI SSE
  returned a nonempty staging-only container list with CPU/memory data.
- Existing stage-only Docker log limits remain. Host Docker production APIs,
  CasaOS app storage and Nextcloud external HDD remain inaccessible.
- All CasaOS production services remain untouched, no production cutover.
- Catalog planning remains 673/726; 53 host-integrated apps require adapters.
