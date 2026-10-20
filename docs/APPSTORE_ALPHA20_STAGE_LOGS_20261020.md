# OpenServerDesk Alpha 0.7.0-alpha.20 — staging-only Docker log API

## Implemented
- Docker compatibility facade supports verified GET /containers/<stage-ID>/logs.
- A container ID must be an exact 64-hex ID returned by provenance-verified
  OpenServerDesk staging registration; protected Qui and production containers
  are not eligible. No caller-supplied host path or Docker endpoint is used.
- Read-only Docker logs subprocess accepts fixed arguments and this ID only,
  with tail <= 160, 64KiB maximum log payload, 5.5 seconds maximum follow
  window, two simultaneous log readers, and Docker stdout/stderr mux frames.
- The common Docker API tail=all request is accepted but safely capped to
  160 lines. Invalid filters, excessive tails, details, unregistered IDs,
  and arbitrary log operations are denied.
- /info reports only verified staging container counts.
- All engine writes (POST/DELETE/PUT/PATCH) remain denied, and the real
  Docker daemon socket is never mounted into third-party containers.
- Four focused log-interface tests verify Docker mux frames, bounded options,
  exact staging-ID authorization, and non-writable endpoints.
- Retain separate andre UID1000 broker/user service and existing Alpha UI.

## Explicit limits
- Stage log readings may contain text emitted by the staging application;
  only the Dozzle pilot has access to the facade socket inside its sandbox.
- The bounded follow window is a 5.5-second read, not an unrestricted
  indefinite Docker log stream or a complete replacement of Dozzle features.
- Dozzle client-side log rendering and reconnect behavior still require
  real runtime UAT; unit tests alone do not prove it.
- Static CasaOS planning 673/726; 53 apps with host integration still require
  distinct adapters. No CasaOS production cutover or external Nextcloud HDD
  access is authorized or performed.
