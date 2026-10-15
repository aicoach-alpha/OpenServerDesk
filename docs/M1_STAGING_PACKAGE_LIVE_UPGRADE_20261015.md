# Real staging package activation and reversible upgrade — 15 Oct 2026

Actual OpenServerDesk staging systemd unit is now running **directly from the
candidate Debian package contents**; not the GitHub source checkout.

Activation and upgrade implementation:
- tools/staging/deploy-packaged-stage.py: exact SHA256 verification, stage-only
  root-owned release extraction, systemd ExecStart override, post-activation
  health, source-application auth protection and six-production-CasaOS-status
  checks; automatic revert to checkout on failed activation.
- tools/staging/upgrade-packaged-stage.py: exact package check, durable undo
  journal before updating override, automatic rollback on failed health,
  crash recovery action and explicit rollback operation to earlier staged
  v0.6.7. Does not modify CasaOS service units or application data.
- Stage release v0.6.7 was activated after fixing filesystem permissions,
  and the exact source version in its health was still the prior component
  version, motivating dynamic version attestation in v0.6.8.
- v0.6.8 package includes release-version.txt; the actual local service
  responds HTTP 200 /health with version=0.6.8; real Docker inventory
  returned 16 containers, unauthorized stage-app GET returned HTTP 401,
  six CasaOS production services stayed active, and migration remains false.
- Staged activation receipts stored root-private under
  /opt/openserverdesk-dev/releases. Live systemd ExecStart resolves to
  /opt/openserverdesk-dev/releases/0.6.8/usr/lib/openserverdesk/server/app.py.

**Caution:** v0.6.8 was built while another checkout file was being edited
and is therefore a functional STAGING deployment, NOT a fully source-frozen,
reproducible, independently signed production release. Never promote it
to CasaOS replacement without addressing all of the following:
  - full upstream AppManagement/LocalStorage integration and authentication;
  - all live Docker/Compose application data consistent backup and restore;
  - safe real-production full-stack cutover plus durable complete rollback;
  - signed, trusted, independently audited reproducible build and security
    acceptance.

No CasaOS production service was stopped or changed. Automatic M1 progress
tasks were disabled at the user's request and remain disabled.
