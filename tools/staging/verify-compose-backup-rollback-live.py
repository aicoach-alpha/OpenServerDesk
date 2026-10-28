#!/usr/bin/env python3
"""One authentic LIVE app install, Compose snapshot, corruption, recovery."""
import json
import secrets
import subprocess
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError

BASE="http://127.0.0.1:18690"
STAGE=Path("/home/andre/projects/openserverdesk/operations/runtime-stage/stage-app-manager")
TOKEN=(STAGE/"token").read_text().strip()


def ids():
    return set(subprocess.check_output(
        ["docker","ps","-a","-q","--no-trunc"],text=True).splitlines())


def api(path,method="GET",body=None):
    h={"Authorization":"Bearer "+TOKEN,"Origin":BASE}
    if body is not None:h["Content-Type"]="application/json"
    req=Request(BASE+path,method=method,headers=h,
                data=json.dumps(body).encode() if body is not None else None)
    try:
        with urlopen(req,timeout=30) as response:
            return response.status,json.load(response)
    except HTTPError as response:
        return response.code,json.load(response)


def main():
    original=ids()
    project=None
    checkpoint=None
    try:
        status,result=api("/api/v1/stage/compose","POST",
            {"action":"install","template":"static-web"})
        assert status==200,(status,result)
        project=result["app"]["project"]
        stage_file=STAGE/"compose-projects"/project/"data/index.html"
        prior=stage_file.read_bytes()
        assert api("/api/v1/stage/recovery","POST",{"action":"checkpoint"})[0]==409
        status,proof=api("/api/v1/stage/compose-backups","POST",{"action":"checkpoint"})
        assert status==200,(status,proof)
        checkpoint=proof["checkpoint"]
        assert proof["projects"]==1
        assert api("/api/v1/stage/compose-backups")[1]["backups"][0]["id"]==checkpoint
        stage_file.write_bytes(("stage-only damaged state "+secrets.token_hex(5)).encode())
        assert stage_file.read_bytes()!=prior
        status,restored=api("/api/v1/stage/compose-backups","POST",{
            "action":"restore","checkpoint":checkpoint,
        })
        assert status==200,(status,restored)
        assert restored["original_user_data_modified"] is False
        assert stage_file.read_bytes()==prior
        assert api("/api/v1/stage/compose")[1]["projects"][0]["running"] is True
        assert not (STAGE/"compose-backups/pending").exists()
        print("LIVE_HTTP_AUTHENTICATED_COMPOSE_CHECKPOINT_CORRUPT_RESTORE_PASS")
        print("INCOMPLETE_LEGACY_STAGE_RESTORE_BLOCKED_PASS")
        status,_=api("/api/v1/stage/compose-backups","POST",{
            "action":"delete","checkpoint":checkpoint,
        })
        assert status==200
        checkpoint=None
        status,_=api("/api/v1/stage/compose","POST",{
            "action":"uninstall","project":project,
        })
        assert status==200
        project=None
        assert ids()==original
        print("EXISTING_PRODUCTION_DOCKER_OBJECT_IDS_UNCHANGED_PASS",len(original))
    finally:
        if checkpoint is not None:
            api("/api/v1/stage/compose-backups","POST",{"action":"delete","checkpoint":checkpoint})
        if project is not None:
            api("/api/v1/stage/compose","POST",{"action":"uninstall","project":project})


if __name__=="__main__":
    main()
