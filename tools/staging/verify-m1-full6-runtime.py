#!/usr/bin/env python3
"""Isolated six ReCasaOS service integration using v0.5.0 installed payload.

No host ports, Docker socket, host network, production configs or live volumes.
The absence of Docker socket means AppManagement's container mutating actions
cannot be considered tested by this isolated boot gate.
"""
import json
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

STAGE=Path("/home/andre/projects/openserverdesk/operations/runtime-stage")
PACKAGE=Path("/home/andre/projects/openserverdesk/operations/build/openserverdesk-m1-candidate_0.5.0_amd64.deb")
IMAGE="golang:1.26.8"


def invoke(*args, allow_error=False):
    r=subprocess.run(args,capture_output=True,text=True,timeout=24)
    if r.returncode and not allow_error:
        raise RuntimeError(f"{args[0]} failed: {r.stderr[-320:]}")
    return r.stdout.strip()


def docker(*args,allow_error=False):
    return invoke("docker",*args,allow_error=allow_error)


def main():
    token=secrets.token_hex(6)
    prefix="osd-m1-six-"+token
    started=[]
    with tempfile.TemporaryDirectory(prefix="m1-six-",dir=STAGE) as temp:
        root=Path(temp)
        package=root/"package"
        package.mkdir()
        invoke("dpkg-deb","--extract",str(PACKAGE),str(package))
        bin_dir=package/"usr/lib/openserverdesk/bin"
        for name in ("casaos","CasaOS-Gateway","CasaOS-MessageBus","CasaOS-UserService","CasaOS-AppManagement","CasaOS-LocalStorage"):
            if not (bin_dir/name).is_file():
                raise RuntimeError("incomplete packaged stack: "+name)
        for name in ("gw-config","bus-config","user-config","core-config","app-config",
                     "storage-config","run","log","core-data","bus-data","user-data",
                     "app-data","store-data","local-data","shell","appstore","apps"):
            (root/name).mkdir(mode=0o700)
        configs={
          "gw-config/gateway.ini":"[common]\nruntimepath=/run/osd-stage\n[gateway]\nport=18701\naddress=127.0.0.1\nhttpsport=0\n",
          "bus-config/message-bus.conf":"[common]\nRuntimePath=/run/osd-stage\n[app]\nLogPath=/var/log/casaos\nLogSaveName=message-bus\nLogFileExt=log\nDBPath=/var/lib/osd-bus\n",
          "user-config/user-service.conf":"[common]\nRuntimePath=/run/osd-stage\n[app]\nLogPath=/var/log/casaos\nLogSaveName=user-service\nLogFileExt=log\nDBPath=/var/lib/osd-user\nUserDataPath=/var/lib/osd-user\n",
          "core-config/casaos.conf":"[app]\nRuntimeRootPath=/run/osd-stage\nLogPath=/var/log/casaos\nDBPath=/var/lib/osd-core\nUserDataPath=/var/lib/osd-core\nShellPath=/usr/share/casaos/shell\n[server]\nRunMode=release\n",
          "app-config/app-management.conf":"[common]\nRuntimePath=/run/osd-stage\n[app]\nLogPath=/var/log/casaos\nDBPath=/var/lib/osd-app\nAppStorePath=/var/lib/osd-app/appstore\nAppsPath=/var/lib/osd-app/apps\n",
          "storage-config/local-storage.conf":"[common]\nRuntimePath=/run/osd-stage\n[app]\nLogPath=/var/log/casaos\nDBPath=/var/lib/osd-storage\nShellPath=/usr/share/casaos/shell\n[server]\nEnableMergerFS=false\n"
        }
        for name,value in configs.items():
            (root/name).write_text(value)
        # Files stay inside disposable staging root; no host sockets/host mount.
        def launch(role,binary,config,cmd,mounts):
            name=prefix+"-"+role
            args=["run","-d","--name",name,"--label","osd.m1.fixture=true",
                  "--label","osd.m1.owner="+token,
                  "--network",("none" if role=="gw" else "container:"+prefix+"-gw"),
                  "--read-only","--cap-drop","ALL","--security-opt","no-new-privileges",
                  "--memory","256m","--pids-limit","100",
                  "--tmpfs","/tmp:rw,nosuid,nodev,size=30m",
                  "--mount",f"type=bind,src={bin_dir/binary},dst=/usr/local/bin/component,readonly",
                  "--mount",f"type=bind,src={root/config},dst=/etc/casaos,readonly",
                  "--mount",f"type=bind,src={root/'run'},dst=/run/osd-stage",
                  "--mount",f"type=bind,src={root/'log'},dst=/var/log/casaos"]
            for src,dst,readonly in mounts:
                args += ["--mount",f"type=bind,src={root/src},dst={dst}"+(",readonly" if readonly else "")]
            args += ["--entrypoint","/usr/local/bin/component",IMAGE,*cmd]
            docker(*args)
            started.append(name)
            return name

        try:
            gw=launch("gw","CasaOS-Gateway","gw-config",
                      ["-w","/var/lib/casaos/www"],
                      [("package/usr/share/openserverdesk/www","/var/lib/casaos/www",True)])
            for _ in range(20):
                if docker("exec",gw,"curl","-fsS","--max-time","2",
                          "http://127.0.0.1:18701/index.html",allow_error=True):
                    break
                time.sleep(.4)
            else:
                raise RuntimeError("Gateway/UI not ready")
            launch("bus","CasaOS-MessageBus","bus-config",
                   ["-c","/etc/casaos/message-bus.conf"],
                   [("bus-data","/var/lib/osd-bus",False)])
            for _ in range(20):
                if (root/"run/message-bus.url").exists():
                    break
                time.sleep(.4)
            else:
                raise RuntimeError("MessageBus not ready")
            launch("user","CasaOS-UserService","user-config",
                   ["-c","/etc/casaos/user-service.conf","-db","/var/lib/osd-user"],
                   [("user-data","/var/lib/osd-user",False)])
            launch("core","casaos","core-config",
                   ["-c","/etc/casaos/casaos.conf","-db","/var/lib/osd-core"],
                   [("core-data","/var/lib/osd-core",False),("shell","/usr/share/casaos/shell",True)])
            launch("app","CasaOS-AppManagement","app-config",
                   ["-c","/etc/casaos/app-management.conf"],
                   [("app-data","/var/lib/osd-app",False)])
            launch("storage","CasaOS-LocalStorage","storage-config",
                   ["-c","/etc/casaos/local-storage.conf","-db","/var/lib/osd-storage"],
                   [("local-data","/var/lib/osd-storage",False),("shell","/usr/share/casaos/shell",True)])
            time.sleep(3)
            for name in started:
                running=docker("inspect",name,"--format","{{.State.Running}}")
                print(name.rsplit("-",1)[-1].upper()+"_RUNNING="+running,flush=True)
                if running!="true":
                    # Output only last few log lines; no user credentials in fixture.
                    print("FAILED_ROLE="+name.rsplit("-",1)[-1],flush=True)
                    raise RuntimeError("isolated component exited: "+name)
            response=docker("exec",gw,"curl","-fsS",
                            "http://127.0.0.1:18701/v1/users/status")
            data=json.loads(response)
            if data.get("data",{}).get("initialized") is not False:
                raise RuntimeError("UserService routed status not fresh")
            print("FULL6_ISOLATED_PROCESS_BOOT_AND_USER_ROUTE_PASS",flush=True)
        finally:
            for name in reversed(started):
                docker("rm","-f",name,allow_error=True)
            print("ISOLATED_FULL6_CLEANUP_COMPLETE",flush=True)


if __name__=="__main__":
    main()
