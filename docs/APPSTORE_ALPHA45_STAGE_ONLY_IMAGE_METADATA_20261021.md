# OpenServerDesk Alpha 0.7.0-alpha.45 — stage-verified image metadata

## Delivered
- Synthetic Docker facade GET /images/json with bounded all/digests flags,
  and GET /images/sha256:<immutable-64hex>/json for exact stage image IDs.
- Each digest comes only from a stage manifest whose actual container
  and image Config.Image have passed the existing full provenance check.
  No host-wide Docker image listing, image inspection, or arbitrary paths.
- Container list and inspect use the actual immutable verified stage
  digest instead of a generic stage-only placeholder.
- Only images used by registered approved staging containers are shown;
  the protected Qui, unregistered folders and pending projects are hidden.
- Response contains sanitized staging labels, digest and usage count;
  no real registry tags or digests, image config, secret, or host image metadata.
- Unknown image IDs return 404. Docker image creation/deletion/pull and
  all other write methods remain denied 403.
- Four narrowly focused tests for stage-only deduplication, forgery
  rejection, Unix API response/write denial and real stage image evidence.
- The previous broker service unexpectedly still pointed at immutable
  release .30. This release updates BOTH alpha and broker service unit
  to .45 and verifies stable systemd-activated socket inode at restart.

## Remaining limitations
- WUD can see stage image IDs, not query registry update availability:
  stage network remains internal-only and repo tags are withheld.
- Image size/creation-time compatibility defaults are zeros, not actual
  host measurements or proof of full WUD compatibility.
- 676/726 static sandbox plans unchanged, NOT full runtime parity.
- CasaOS production and Nextcloud external HDD files remain untouched.
