# Alpha .40 — Glances stage-only non-root identity fix

Observed direct real-image failure under UID1000: Glances imported
getpass.getuser(), which raised KeyError because its image does not
have a passwd entry for that numeric UID. A bounded no-network,
read-only diagnostic confirmed that USER=stageglances and
LOGNAME=stageglances permit Glances import without UID escalation.

This release pins the two environment variables only for the
exact-approved, digest-pinned Glances catalogue pilot.
Existing GLANCES_OPT=-w, UID/GID 1000:1000, no host PID
namespace, cap_drop ALL, internal-only stage network and synthetic
read-only Docker facade socket remain unchanged.

Targeted five-test compiler and runtime suite PASS. A live
stage install and private HTTP test must be performed separately
before functional Glances readiness is claimed.
CasaOS production and Nextcloud external HDD are out of scope.
