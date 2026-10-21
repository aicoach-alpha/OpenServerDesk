# CasaOS production Legacy app tiles — October 21, 2026

## Root cause confirmed (actual installed CasaOS frontend)
The native CasaOS dashboard at port 8090 renders oldAppList in
/var/lib/casaos/www/src_views_Home_vue.90220776.js. Unknown Docker
containers (app_type == container) are shown under
Legacy app (To be rebuilt). The user screenshot is native CasaOS, NOT
the OpenServerDesk Alpha frontend on port 18691.

## Safe immediate correction performed
The three stopped, non-restarting Docker containers named osd-m1-user,
osd-m1-bus, and osd-m1-gateway were retired. Each was verified to
use golang:1.26.8, only exact OSD stage bind mounts, no Docker volumes,
no host ports, no third-party namespace dependents, and status exited.
The cleanup used only docker rm <full id> WITHOUT force or volumes.
No staging bind data, CasaOS app, Nextcloud or OmniRush container was
deleted. Preflight + three small safety tests passed.

The repeatable, idempotent script is
tools/staging/reconcile_casaos_legacy_osd_m1.py; it is dry-run by
default and only permits those three exact historical M1 container
identities. It is NOT a broad Docker prune tool.

## Remaining Legacy tiles are not safe garbage
The registered osd-compiled-9696c93402e4 project has a running Qui
service and PostgreSQL, and osd-compiled-e62e0799577d runs MySpeed.
These are live, provenance-verified, preserved stage projects.
omnirush-box-* belongs to a separate OmniRush tool; some are active
and a stopped canary still exists. No OmniRush object was mutated.

## Reversible presentation-only cleanup — NOT installed automatically
The optional CSS at deploy/casaos/legacy_development_cards.css
hides development-namespaced Legacy tiles without stopping or deleting
containers, and hides the heading only when there are no other genuine
legacy applications. CasaOS already loads /css/custom.css, but
/var/lib/casaos/www/css/custom.css is root-owned (0644).
The andre uid 1000 execution profile has no authorized direct
write to this file. Therefore the CSS override was NOT installed.
An explicit administrator-controlled approval/install should back up
the original CSS first and append the staged block, rather than
overwriting other customizations. Removing the block reverses it.

A presentation filter is NOT resource cleanup or replacement for a
dedicated staging Docker engine. Avoid proliferating shared-host test
containers in future; test workloads should be ephemeral and cleanup
must verify ownership before deletion.

## Invariants
- CasaOS production services remain 6/6 active.
- Existing stage Qui/MySpeed remain registered and running.
- The external Nextcloud data HDD remains outside all inspection and
  cleanup operations.
- No bulk docker system prune, volume removal, or image cleanup.
