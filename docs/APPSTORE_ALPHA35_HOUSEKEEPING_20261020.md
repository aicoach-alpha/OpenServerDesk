# OpenServerDesk Alpha 0.7.0-alpha.35 — nonintrusive staging housekeeping

## Implemented
- Dedicated collapsed housekeeping section below managed App Store projects;
  unregistered staging folders never appear as normal application rows.
- Displays the complete authenticated staging inventory with an ID filter,
  8 entries per page, previous/next navigation and matching/total counts.
- Retains the existing authenticated explicit Clean only if empty action,
  confirmation and backend fail-closed ownership/data/network verification.
  Clicking this button does not change any registered app or CasaOS production.
- The underlying listing endpoint is queried once per normal refresh;
  pagination and filtering are local-only and never enumerate host data.
- The UI reads only previously provided sanitized project IDs and creates
  textContent nodes, not unsanitized markup or filesystem path links.
- No mass deletion, background cleanup or batch mutation of historical
  directories. All 15 historical unregistered folders remain unchanged.
- One focused Node UI test checks 15 folders produce 2 pages (8+7),
  filtering, empty match, page clamping, and separation of housekeeping UI.

## Remaining work
- Eligibility preview remains conservative; operator may only attempt the
  validated cleanup after confirmation. Rejected directories are retained.
- Safe App Store plans are not proof of functional parity, and CasaOS
  production cutover remains explicitly blocked.
- External Nextcloud HDD user files and original CasaOS volumes untouched.
