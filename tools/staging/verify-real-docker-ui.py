#!/usr/bin/env python3
"""One targeted REAL read-only local Docker Engine integration and UI check."""
import http.client
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO=Path(__file__).resolve().parents[2]


def check():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port=sock.getsockname()[1]
    env={**os.environ, "OSD_HOST":"127.0.0.1",
         "OSD_PORT":str(port),"OSD_DOCKER_READ_ONLY":"1"}
    service=subprocess.Popen([sys.executable,"-B",str(REPO/"server/app.py")],
                             env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    url=f"http://127.0.0.1:{port}"
    try:
        for _ in range(25):
            try:
                with urlopen(url+"/health", timeout=1) as r:
                    if json.load(r)["status"]=="ok":
                        break
            except OSError:
                time.sleep(.1)
        else: raise RuntimeError("staging HTTP startup failed")
        with urlopen(url+"/api/v1/docker/containers",timeout=6) as r:
            assert r.status==200
            data=json.load(r)
        actual=subprocess.check_output(["docker","ps","-a","--format","{{.ID}}"],
                                        text=True).splitlines()
        assert data["container_count"]==len(actual),(data["container_count"],len(actual))
        assert any(c["name"] for c in data["containers"])
        assert all(set(c)<=set(("id","name","image","state","status","compose_project","ports"))
                   for c in data["containers"])
        assert data["source"]=="local_docker_engine_read_only"
        with urlopen(url+"/ui",timeout=3) as r:
            assert r.status==200 and b"OpenServerDesk" in r.read()
            assert "default-src 'none'" in r.headers["Content-Security-Policy"]
        with urlopen(url+"/ui/app.js",timeout=3) as r:
            script=r.read()
            assert b"textContent" in script and b"innerHTML" not in script
        try:
            urlopen(Request(url+"/api/v1/docker/containers",data=b"{}"),timeout=3)
            raise AssertionError("POST to read-only inventory allowed")
        except HTTPError as err:
            assert err.code==405
        with urlopen(url+"/api/v1/capabilities",timeout=3) as r:
            caps=json.load(r)
        assert caps["production_changes"] is False and caps["docker_write"] is False
        print("REAL_DOCKER_INVENTORY_AND_USABLE_UI_PASS")
        print("CONTAINERS_READ_ONLY",data["container_count"])
        print("COMPOSE_PROJECTS_READ_ONLY",len(data["compose_projects"]))
        print("MUTATION_REJECTED_PASS")
    finally:
        service.terminate()
        try:service.wait(timeout=5)
        except subprocess.TimeoutExpired:service.kill();service.wait()


if __name__=="__main__":
    check()
