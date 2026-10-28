#!/usr/bin/env python3
"""Actual authenticated API lifecycle, isolated stage Compose only."""
import json
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE = "http://127.0.0.1:18690"
TOKEN = Path(
    "/home/andre/projects/openserverdesk/operations/runtime-stage/stage-app-manager/token"
).read_text().strip()


def docker_ids():
    return set(subprocess.check_output(
        ["docker", "ps", "-a", "-q", "--no-trunc"], text=True
    ).splitlines())


def req(path, method="GET", body=None, auth=True, origin=None):
    headers = {"Origin": (
        "http://127.0.0.1:18690" if origin is None else origin
    )}
    if auth:
        headers["Authorization"] = "Bearer " + TOKEN
    if body is not None:
        headers["Content-Type"] = "application/json"
    data = json.dumps(body).encode() if body is not None else None
    request = Request(BASE+path, method=method, data=data, headers=headers)
    try:
        with urlopen(request, timeout=45) as resp:
            return resp.status, json.load(resp)
    except HTTPError as err:
        return err.code, json.load(err)


def main():
    baseline=docker_ids()
    project=None
    try:
        assert req("/api/v1/stage/compose", auth=False)[0] == 401
        assert req("/api/v1/stage/catalog", auth=False)[0] == 401
        assert req("/api/v1/stage/compose", origin="http://attacker.test")[0] == 403
        status,catalog=req("/api/v1/stage/catalog")
        assert status==200 and len(catalog["templates"])==2
        assert req("/api/v1/stage/compose","POST",{"action":"install","template":"nextcloud:latest"})[0]==400
        assert req("/api/v1/stage/compose","POST",{"action":"stop","project":"casaos-gateway"})[0]==404
        assert req("/api/v1/stage/compose","POST",{"action":"install","template":"static-web",
                                                   "mount":"/mnt/data/nextcloud"})[0]==400
        status,result=req("/api/v1/stage/compose","POST",
                          {"action":"install","template":"static-web"})
        assert status==200,(status,result)
        app=result["app"]
        project=app["project"]
        assert app["running"] is True and app["isolated"] is True
        created=docker_ids()-baseline
        assert len(created)==1
        container=next(iter(created))
        for _ in range(12):
            p=subprocess.run(
                ["docker","exec",container,"wget","-qO-",
                 "http://127.0.0.1:8080/index.html"],
                text=True,capture_output=True,timeout=15)
            if p.returncode==0:break
            time.sleep(0.2)
        assert p.returncode==0 and "OpenServerDesk" in p.stdout
        assert req("/api/v1/stage/compose")[1]["projects"][0]["project"]==project
        status,stopped=req("/api/v1/stage/compose","POST",{"action":"stop","project":project})
        assert status==200 and not stopped["app"]["running"]
        status,started=req("/api/v1/stage/compose","POST",{"action":"start","project":project})
        assert status==200 and started["app"]["running"]
        status,restarted=req("/api/v1/stage/compose","POST",{"action":"restart","project":project})
        assert status==200 and restarted["app"]["running"]
        assert req("/api/v1/stage/compose","POST",
                   {"action":"stop","project":"/mnt/data/nextcloud"})[0]==404
        status,deleted=req("/api/v1/stage/compose","POST",{"action":"uninstall","project":project})
        assert status==200 and deleted["stage_data_retained"] is True
        project=None
        assert docker_ids()==baseline
        assert req("/api/v1/stage/compose")[1]["projects"]==[]
        print("AUTHENTICATED_COMPOSE_CATALOG_LIFECYCLE_HTTP_E2E_PASS")
        print("TEMPLATE_ALLOWLIST_HOST_BIND_AND_CASAOS_MUTATION_DENIED_PASS")
        print("LIVE_STAGE_COMPOSE_HTTP_AND_PERSISTENT_DATA_PASS")
        print("PRODUCTION_PREEXISTING_CONTAINER_IDS_UNCHANGED_PASS",len(baseline))
    finally:
        if project is not None:
            req("/api/v1/stage/compose","POST",{"action":"uninstall","project":project})


if __name__ == "__main__":
    main()
