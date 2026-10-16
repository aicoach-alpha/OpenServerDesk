#!/usr/bin/env python3
"""Test each incumbent app STRUCTURE using stage-only BusyBox containers.

Never runs any incumbent image, command, app environment, published port or
production data mount. No network. The entire staging project is ephemeral;
every created container has an exact ownership label and is removed.
"""
from __future__ import annotations
import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tools"))
from acceptance_m1_compose_compat import CONFIG,safe_project_config
from synthetic_compose_rehearsal import synthetic

STAGE=Path("/opt/openserverdesk-dev/runtime-stage")
PREFIX="osd-fixture-"


def docker(*cmd,timeout=40,allowed=False):
    result=subprocess.run(["docker",*cmd],capture_output=True,text=True,timeout=timeout)
    if result.returncode and not allowed:
        raise RuntimeError("Docker staging lifecycle command failed")
    return result


def baseline():
    result=docker("ps","-a","--no-trunc","--format","{{.ID}}")
    return set(result.stdout.splitlines())


def test_one(source_file:Path):
    doc=safe_project_config(source_file)
    fixture, analysis=synthetic(doc)
    ident=secrets.token_hex(5)
    project=PREFIX+ident
    fixture["name"]=project
    # All containers carry immutable project-scoped stage ownership labels.
    for _,service in fixture["services"].items():
        service["labels"]={
            "osd.m1.synthetic":"stage-only",
            "osd.m1.fixture-owner":ident
        }
    with tempfile.TemporaryDirectory(prefix="osd-compose-exec-",dir=STAGE) as tmp:
        config=Path(tmp)/"compose.json"
        config.write_text(json.dumps(fixture,sort_keys=True))
        options=("-f",str(config),"-p",project)
        before=baseline()
        try:
            docker("compose",*options,"config","--quiet")
            docker("compose",*options,"up","-d","--pull","never","--no-build",timeout=55)
            containers=docker("ps","-a","--no-trunc","--filter",
                              "label=com.docker.compose.project="+project,
                              "--format","{{.ID}}").stdout.splitlines()
            if len(containers)!=analysis["service_count"]:
                raise RuntimeError("unexpected number of synthetic services")
            for container_id in containers:
                raw=docker("inspect","--type","container",container_id).stdout
                item=json.loads(raw)[0]
                config_data=item["Config"]
                labels=config_data["Labels"]
                host=item["HostConfig"]
                mounts=item.get("Mounts") or []
                if not all([
                    labels.get("osd.m1.synthetic")=="stage-only",
                    labels.get("osd.m1.fixture-owner")==ident,
                    config_data.get("Image")=="busybox:latest",
                    host.get("NetworkMode")=="none",
                    host.get("ReadonlyRootfs") is True,
                    host.get("Privileged") is False,
                    not host.get("PortBindings"),
                    not mounts,
                    bool(item["State"].get("Running")),
                ]):
                    raise RuntimeError("synthetic service escaped staging boundary")
            return analysis["service_count"]
        finally:
            # Do NOT remove any production container by name or ID.
            # Compose file + unpredictable project identify only THIS fixture.
            docker("compose",*options,"down","--remove-orphans",timeout=55,allowed=True)
            if baseline()!=before:
                raise RuntimeError("Docker container inventory not restored after fixture")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--start",type=int,default=1)
    parser.add_argument("--end",type=int,default=18)
    opts=parser.parse_args()
    if not 1<=opts.start<=opts.end<=18 or opts.end-opts.start>8:
        raise RuntimeError("batch must contain at most 9 safe stage applications")
    image=docker("image","inspect","busybox:latest",allowed=True)
    if image.returncode:
        raise RuntimeError("required locally cached BusyBox image unavailable")
    apps=sorted(
        p/"docker-compose.yml" for p in CONFIG.iterdir()
        if not p.is_symlink() and p.is_dir()
        and not (p/"docker-compose.yml").is_symlink()
        and (p/"docker-compose.yml").is_file()
    )
    if len(apps)!=18:
        raise RuntimeError("expected installed configuration baseline changed")
    total=0
    for index in range(opts.start,opts.end+1):
        count=test_one(apps[index-1])
        total+=count
        # No source names, ports, secrets, images or mount paths in output.
        print("SYNTHETIC_APP_STRUCTURE",index,"SERVICE_COUNT",count,flush=True)
    print(json.dumps({
        "scope":"ISOLATED_SYNTHETIC_COMPOSE_LIFECYCLE",
        "source_app_structures":len(apps),
        "start_index":opts.start,"end_index":opts.end,
        "synthetic_apps_verified_in_this_batch":opts.end-opts.start+1,
        "synthetic_services_started_then_removed":total,
        "original_application_images_executed":False,
        "production_modified":False,
        "nextcloud_uploads_accessed":False,
        "real_app_imports_verified":0,
        "production_parity_claim":False,
    },sort_keys=True))


if __name__=="__main__":
    main()
