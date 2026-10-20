# OpenServerDesk Alpha 0.7.0-alpha.34 — operator-only empty scaffold reclaim

## Implemented
- Authenticated staging operators can explicitly request clean-preparation
  on a previously unregistered osd-compiled stage directory.
- An orphan appears in the App Store lifecycle table with a disabled control
  when staging write authentication is not granted.
- A confirmation explains that ONLY verified empty preparation scaffolding
  may be removed. Neither a registered app nor retained nonempty volume,
  custom file, symlink, mount point, foreign-owned file, or Docker resource
  can be removed by this action.
- The directory must have been idle at least ten minutes and the exact
  reclaimer from Alpha 0.7.0-alpha.33 revalidates the project, namespace,
  owner, allowed generated files and empty volume directories.
- The UI displays the result and refreshes the live registry. Refusal leaves
  evidence intact for operator review.
- Three focused tests verify successful removal of empty generated metadata,
  preservation of retained volume contents, and rejection of fresh or
  already registered stage projects.
- The existing auto-cleanup at failed preparation remains in Alpha .33.

## Boundaries
- No wildcard cleanup, no CLI shell exposure, no full filesystem scan.
- The staging App Store table displays at most six unregistered directory
  entries, and does not traverse or disclose their file contents.
- No mutation to production CasaOS, its containers or the external Nextcloud
  HDD. Retained stage data is never deleted by this operation.
- All old root-protected staging directories remain protected.
- App Store functional parity and CasaOS production cutover remain outside
  the release acceptance criteria.
