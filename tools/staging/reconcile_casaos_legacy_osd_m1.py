#!/usr/bin/env python3
"""Remove only three retired, exited OSD M1 Docker test containers.

Never changes CasaOS apps or services, project data, images, networks,
volumes, or running containers. Dry-run by default. No sudo required.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

STAGE_ROOT=Path("/home/andre/projects/openserverdesk/operations")
NAMES=("osd-m1-user","osd-m1-bus","osd-m1-gateway")
EXPECTED_MOUNTS={
    "osd-m1-user":{
        "/home/andre/projects/openserverdesk/operations/runtime-stage/user-conf",
        "/home/andre/projects/openserverdesk/operations/runtime-stage/run",
        "/home/andre/projects/openserverdesk/operations/runtime-stage/user-db",
        "/home/andre/projects/openserverdesk/operations/runtime-stage/log",
        "/home/andre/projects/openserverdesk/operations/bin/CasaOS-UserService",
    },
    "osd-m1-bus":{
        "/home/andre/projects/openserverdesk/operations/runtime-stage/bus-conf",
        "/home/andre/projects/openserverdesk/operations/runtime-stage/run",
        "/home/andre/projects/openserverdesk/operations/runtime-stage/bus-data",
        "/home/andre/projects/openserverdesk/operations/runtime-stage/log",
        "/home/andre/projects/openserverdesk/operations/bin/CasaOS-MessageBus",
    },
    "osd-m1-gateway":{
        "/home/andre/projects/openserverdesk/operations/runtime-stage/conf",
        "/home/andre/projects/openserverdesk/operations/runtime-stage/run",
        "/home/andre/projects/openserverdesk/operations/runtime-stage/log",
        "/home/andre/projects/openserverdesk/operations/bin/CasaOS-Gateway",
        "/home/andre/projects/openserverdesk/operations/runtime-stage/www",
    },
}

def command(*args):
    result=subprocess.run(("docker",*args),capture_output=True,text=True,
                          timeout=25,check=False)
    if result.returncode:
        raise RuntimeError("Docker action refused: "+str(args[:2]))
    return result.stdout.strip()

def inspect_all():
    ids=command("ps","-a","-q","--no-trunc").splitlines()
    if len(ids)>2000 or any(len(i)!=64 for i in ids):
        raise RuntimeError("Unexpected Docker inventory")
    if not ids:
        return []
    records=json.loads(command("inspect",*ids))
    if not isinstance(records,list) or len(records)!=len(ids):
        raise RuntimeError("Incomplete Docker inspection")
    return records

def preflight(records):
    if not isinstance(records,list):
        raise RuntimeError("Invalid inventory")
    by_name={item.get("Name","").lstrip("/"):item for item in records}
    targets=[]
    for name in NAMES:
        entry=by_name.get(name)
        if entry is None:
            continue  # Already removed is fine; this script is idempotent.
        state=entry.get("State") or {}
        host=entry.get("HostConfig") or {}
        config=entry.get("Config") or {}
        mounts=entry.get("Mounts") or []
        ident=entry.get("Id")
        if (not isinstance(ident,str) or len(ident)!=64 or
            any(c not in "0123456789abcdef" for c in ident)
            or state.get("Status")!="exited"
            or (host.get("RestartPolicy") or {}).get("Name")!="no"
            or config.get("Image")!="golang:1.26.8"
            or config.get("Volumes")
            or config.get("Labels")
            or host.get("PortBindings")
            or host.get("Privileged")
            or not isinstance(mounts,list)
            or {m.get("Source") for m in mounts}!=EXPECTED_MOUNTS[name]
            or any(m.get("Type")!="bind" for m in mounts)):
            raise RuntimeError("Refuse unexpected lifecycle/data: "+name)
        targets.append(entry)
    candidates={e["Id"] for e in targets}
    gateway=by_name.get("osd-m1-gateway",{})
    gateway_id=gateway.get("Id")
    for entry in targets:
        name=entry["Name"].lstrip("/")
        network=(entry.get("HostConfig") or {}).get("NetworkMode")
        if name=="osd-m1-gateway":
            if network!="none":
                raise RuntimeError("Refuse changed gateway networking")
        elif not isinstance(gateway_id,str) or network not in (
                "container:"+gateway_id,"container:osd-m1-gateway"):
            raise RuntimeError("Refuse changed stage namespace: "+name)
    for other in records:
        if other.get("Id") in candidates:
            continue
        mode=(other.get("HostConfig") or {}).get("NetworkMode","")
        if isinstance(mode,str) and mode.startswith("container:"):
            if (mode.split(":",1)[1] in candidates or
                mode.split(":",1)[1] in NAMES):
                raise RuntimeError("Refuse active outside namespace dependent")
    return [entry["Id"] for entry in targets]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply",action="store_true",
                        help="delete only verified, exited, retired M1 test containers")
    args=parser.parse_args()
    records=inspect_all()
    ids=preflight(records)
    result={"scope":"retired_exited_osd_m1_containers_only",
            "containers":[name for name in NAMES if any(
                i.get("Name")=="/"+name for i in records)],
            "resource_data_deleted":False,
            "volumes_deleted":False,
            "production_containers_touched":False,
            "mode":"apply" if args.apply else "dry_run"}
    if args.apply:
        # Remove dependent namespace containers before their stopped gateway.
        # No -f, -v, volume prune, image remove, or project-wide compose down.
        by_id={i["Id"]:i for i in records}
        for ident in ids:
            name=by_id[ident]["Name"].lstrip("/")
            command("rm",ident)
            print("REMOVED_RETIRED_TEST_CONTAINER",name)
        result["removed"]=len(ids)
    else:
        result["eligible"]=len(ids)
    print(json.dumps(result,sort_keys=True))
    return 0

if __name__=="__main__":
    try:sys.exit(main())
    except (RuntimeError,ValueError,KeyError,TypeError,
            OSError,subprocess.TimeoutExpired) as exc:
        print("REFUSED_CLEANUP:",exc,file=sys.stderr)
        sys.exit(3)
