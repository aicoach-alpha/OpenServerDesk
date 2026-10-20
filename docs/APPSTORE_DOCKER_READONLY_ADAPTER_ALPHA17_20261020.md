# OpenServerDesk 0.7.0-alpha.17 — Stage Docker read-only facade

## Implemented
- Synthetic Unix socket Docker API facade, separate systemd user service
  for andre UID1000. NOT the actual Docker daemon socket.
- Exact GET routes: /_ping, /version, /info, /containers/json,
  /containers/<verified-stage-ID>/json. Every Docker mutation denied.
  Log streams, volumes, images, engine, events, networks denied.
- Data comes from provenance-verified OSD-owned stage projects only.
  Never exposes protected Qui, original host bind mounts, host networks,
  secrets, external HDD or CasaOS production containers.
- Socket owner UID1000, mode 0600, NoNewPrivileges, CPU/memory limits,
  max eight simultaneous requests.
- Compiler curated pilot ONLY for digest-pinned Dozzle definition.
  Original host docker.sock source removed, replaced by synthetic socket.
  Exact service labels, read-only mode, socket file type and mount source
  are verified on every stage operation. Backups exclude the socket.
- Safe static plans 673/726, host-adapter blocked 53, metadata 0.

## Remaining limits
- No Dozzle image in local Docker cache. No claim that its UI runs.
- Synthetic facade has no log streaming; Dozzle's full functions still
  require implementation and evidence.
- No uncontrolled Docker operations, privileged devices or root access.
- 673 denotes static plans, NOT 673 successful runtime UATs.
- CasaOS production cutover NOT approved; all user Nextcloud HDD data
  remains untouched.

## Service
- Alpha HTTPS https://osd.vervue.my.id
- LAN origin 192.168.31.31:18691
- user systemd service openserverdesk-stage-docker-broker.service
