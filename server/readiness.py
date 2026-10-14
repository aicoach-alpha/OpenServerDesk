"""Read-only compatibility checks, never triggers migration."""
import json
from pathlib import Path

def readiness():
    db=Path("/run/openserverdesk/preflight.json")
    if not db.is_file():
        return {"status":"blocked","reason":"preflight_missing","migration_allowed":False}
    try:
        data=json.loads(db.read_text())
        checks=data.get("checks",{})
        if not isinstance(checks,dict) or not checks or not all(v is True for v in checks.values()):
            return {"status":"blocked","reason":"preflight_failed","migration_allowed":False}
        return {"status":"preflight_pass","casaos_version":str(data.get("casaos_version","unknown")),
                "checks_passed":len(checks),"migration_allowed":False,
                "reason":"full_restore_and_activation_rollback_unverified"}
    except (OSError,ValueError,TypeError):
        return {"status":"blocked","reason":"preflight_invalid","migration_allowed":False}
