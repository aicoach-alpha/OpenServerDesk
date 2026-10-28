#!/usr/bin/env python3
"""Verify installed 0.6.0 Debian payload serves REAL local Docker read-only inventory."""
import hashlib
import json
import os
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT=Path("/home/andre/projects/openserverdesk/operations/runtime-stage")
PKG=Path("/home/andre/projects/openserverdesk/operations/build/openserverdesk-m1-candidate_0.6.0_amd64.deb")


def verify():
    with tempfile.TemporaryDirectory(prefix="m1-installed-docker-ui-",dir=ROOT) as scratch:
        temp=Path(scratch)
        os.chmod(temp,0o755)
        installed=temp/"root"
        (installed/"var/lib/dpkg/updates").mkdir(parents=True)
        (installed/"var/lib/dpkg/info").mkdir()
        (installed/"var/lib/dpkg/status").write_text("")
        subprocess.run(["dpkg","--root="+str(installed),"--install",str(PKG)],
                       check=True,stdout=subprocess.DEVNULL)
        script=installed/"usr/lib/openserverdesk/server/app.py"
        assert script.is_file()
        assert (script.parent/"docker_readonly.py").is_file()
        assert (script.parent/"ui/index.html").is_file()
        assert (installed/"usr/lib/openserverdesk/bin/CasaOS-AppManagement").is_file()
        os.chmod(installed,0o755)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1",0))
            port=sock.getsockname()[1]
        base=f"http://127.0.0.1:{port}"
        process=subprocess.Popen(
            ["runuser","-u","andre","--","env","OSD_HOST=127.0.0.1",
             "OSD_PORT="+str(port),"OSD_DOCKER_READ_ONLY=1",
             "/usr/bin/python3","-B",str(script)],
            start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            for _ in range(40):
                try:
                    with urlopen(base+"/api/v1/docker/containers",timeout=2) as result:
                        inventory=json.load(result)
                    break
                except (OSError,TimeoutError):
                    time.sleep(.1)
            else:raise RuntimeError("installed Docker UI did not boot")
            actual=subprocess.check_output(["docker","ps","-a","--format","{{.ID}}"],
                                           text=True).splitlines()
            assert inventory["container_count"]==len(actual)
            assert all("Env" not in c and "Mounts" not in c and "Labels" not in c
                       for c in inventory["containers"])
            with urlopen(base+"/ui",timeout=2) as result:
                assert b"OpenServerDesk" in result.read()
                assert result.status==200
            try:
                urlopen(Request(base+"/api/v1/docker/containers",data=b"{}"),timeout=2)
                raise AssertionError("mutation request permitted")
            except HTTPError as err:
                assert err.code==405
            print("PACKAGED_REAL_DOCKER_UI_AND_COMPOSE_INTEGRATION_PASS")
            print("REAL_ENGINE_CONTAINERS",inventory["container_count"])
            print("REAL_COMPOSE_PROJECTS",len(inventory["compose_projects"]))
            print("PRODUCTION_MUTATION_REJECTED_PASS")
        finally:
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL)
                process.wait()

if __name__=="__main__":
    verify()
