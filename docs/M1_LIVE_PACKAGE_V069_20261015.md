# OpenServerDesk M1 v0.6.9 live, isolated staging integration

Time window: 15 October 2026, approx. 18:59–19:01 WIB.
Scope: **OpenServerDesk staging only**. CasaOS production not changed.

Installed exact Debian artifact:
- /opt/openserverdesk-dev/build/openserverdesk-m1-candidate_0.6.9_amd64.deb
- SHA256: 9e798006f2deac0bea87aaa431641fb799f61fb85cbecd89e9ec4515a741008e
- Actual active systemd stage ExecStart:
  /opt/openserverdesk-dev/releases/0.6.9/usr/lib/openserverdesk/server/app.py
- Release health: version=0.6.9; staging environment.
- Upgrade controller tools/staging/upgrade-packaged-stage-069.py wrote a
  pre-activation recovery journal, validated exact prior 0.6.8 target, and
  verified post-upgrade health/authentication/real Docker state. Versioned
  rollback remains available; production CasaOS services unchanged.

An authentic installed-release end-to-end exercised the authenticated
live stage HTTP API, not GitHub source directly:
- Created a confined stage file, installed a real isolated BusyBox
  Docker container, and read the file from inside the container
- Created a stage checkpoint, corrupted the stage file, restored the
  saved data, read it again from host API and running stage container,
  restarted the stage container and reverified persistence
- Uninstalled the stage container, removed its test file/checkpoint, and
  verified the set of all 16 preexisting production Docker container IDs
  was identical before and after the test
- Confirmed an unauthenticated stage API call was rejected.

Observed:
ACTUAL_LIVE_INSTALLED_AUTH_APP_STORAGE_CHECKPOINT_RESTORE_PASS 0.6.9
APP_STORAGE_PERSISTENCE_AFTER_RESTART_PASS
ALL_PRODUCTION_DOCKER_IDENTITIES_PRESERVED_PASS 16

This does not validate full ReCasaOS AppManagement/LocalStorage APIs,
production Docker management or public multi-user authentication, consistent
real cold backup of all source data, real CasaOS cutover, signed release or
independent security acceptance. Therefore M1 FULL PASS remains blocked and
migration_allowed must remain false.
