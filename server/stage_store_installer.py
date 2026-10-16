"""First native CasaOS store image install pilot, on a strictly isolated stage.

Only trusted, exact, locally available CasaOS AppStore image may be launched.
Never execute the original Compose payload. Never mount original host bind
paths, Nextcloud user HDD, Docker socket, or publish host ports.
"""
from __future__ import annotations
import json
import os
import re
import secrets
import subprocess
import time
from pathlib import Path
import yaml
from stage_apps import STAGE, AppError, guarded, registry
from casaos_appstore import STORE_ROOT, _safe_path

ROOT=STAGE/"appstore-pilot"
REGISTRY=ROOT/"registry.json"
IMAGE="germannewsmaker/myspeed:1.0.8"
APP_ID="default:MySpeed"
CANDIDATE=STORE_ROOT/"default"/"Apps"/"MySpeed"/"docker-compose.yml"
PROJECT_RE=re.compile(r"osd-m1-store-[a-f0-9]{12}\Z")
CID_RE=re.compile(r"[a-f0-9]{64}\Z")
DATA_TARGET="/myspeed/data"

def _run(*args, timeout=50):
    try:
        p=subprocess.run(("docker",*args),capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired):
        raise AppError("staging_store_docker_unavailable",503)
    if p.returncode or len(p.stdout)>100000:
        raise AppError("staging_store_docker_command_failed",503)
    return p.stdout.strip()

def _catalog_image():
    if not _safe_path(CANDIDATE,STORE_ROOT) or not CANDIDATE.is_file():
        raise AppError("native_casaos_app_manifest_unavailable",503)
    try:
        raw=CANDIDATE.read_text()
        if len(raw)>262144:
            raise ValueError("oversized")
        doc=yaml.safe_load(raw)
    except (OSError,UnicodeError,ValueError,yaml.YAMLError):
        raise AppError("native_casaos_app_manifest_invalid",503)
    services=doc.get("services") if isinstance(doc,dict) else None
    if not isinstance(services,dict) or len(services)!=1:
        raise AppError("native_casaos_app_manifest_changed",503)
    service=next(iter(services.values()))
    if not isinstance(service,dict) or service.get("image")!=IMAGE:
        raise AppError("native_casaos_app_image_changed",503)
    return IMAGE

def _root():
    if ROOT.is_symlink():
        raise AppError("unsafe_appstore_pilot_directory",503)
    if not ROOT.exists():
        ROOT.mkdir(mode=0o700)
    if not ROOT.is_dir() or ROOT.stat().st_mode&0o077:
        raise AppError("unsafe_appstore_pilot_directory",503)
    return ROOT

def _data_dir(project):
    if not PROJECT_RE.fullmatch(project):
        raise AppError("invalid_staging_store_id",400)
    folder=_root()/project
    data=folder/"data"
    if folder.is_symlink() or data.is_symlink():
        raise AppError("unsafe_staging_store_data",403)
    return data

def _registry():
    if REGISTRY.is_symlink():
        raise AppError("unsafe_store_registry",503)
    if not REGISTRY.is_file():
        return {}
    try:
        raw=json.loads(REGISTRY.read_text())
        if not isinstance(raw,dict) or len(raw)>1:
            raise ValueError("invalid registry")
        for key,entry in raw.items():
            if (not PROJECT_RE.fullmatch(key) or not isinstance(entry,dict)
                or set(entry)!={"id","owner","app_id"}
                or not CID_RE.fullmatch(entry["id"])
                or not re.fullmatch("[a-f0-9]{32}",entry["owner"])
                or entry["app_id"]!=APP_ID):
                raise ValueError("invalid entry")
        return raw
    except (ValueError,TypeError,OSError):
        raise AppError("appstore_registry_invalid",503)

def _save(entries):
    path=_root()/(".store-pilot-"+secrets.token_hex(8))
    try:
        with path.open("x") as f:
            json.dump(entries,f,sort_keys=True)
            f.flush();os.fsync(f.fileno())
        path.chmod(0o600)
        os.replace(path,REGISTRY)
    finally:
        path.unlink(missing_ok=True)

def _inspect(project,entry):
    container=entry["id"]
    data=_data_dir(project)
    if not data.is_dir() or data.is_symlink():
        raise AppError("staged_appstore_data_unavailable",503)
    try:
        obj=json.loads(_run("inspect","--type","container",container,timeout=20))[0]
    except (ValueError,TypeError,KeyError,IndexError):
        raise AppError("store_container_inspection_failed",503)
    cfg=obj.get("Config") or {}
    host=obj.get("HostConfig") or {}
    labels=cfg.get("Labels") or {}
    mounts=obj.get("Mounts") or []
    if (obj.get("Id")!=container or cfg.get("Image")!=IMAGE
        or cfg.get("User")!="1000:1000"
        or labels.get("osd.m1.store")!="isolated-pilot"
        or labels.get("osd.m1.store.project")!=project
        or labels.get("osd.m1.store.owner")!=entry["owner"]
        or labels.get("osd.m1.store.app")!=APP_ID
        or host.get("Privileged") is not False
        or host.get("NetworkMode")!="none"
        # This real MySpeed image must create local runtime files in its
        # ephemeral container root. They vanish with the container; no host
        # filesystem other than its dedicated staging mount is accessible.
        or host.get("ReadonlyRootfs") is not False
        or host.get("PortBindings")
        or len(mounts)!=1 or mounts[0].get("Type")!="bind"
        or mounts[0].get("Source")!=str(data)
        or mounts[0].get("Destination")!=DATA_TARGET
        or mounts[0].get("RW") is not True):
        raise AppError("staged_store_container_provenance_violation",403)
    state=obj.get("State") or {}
    return {"project":project,"app_id":APP_ID,"image":IMAGE,
            "running":bool(state.get("Running")),
            "state":"running" if state.get("Running") else "stopped",
            "isolated":True,"production_mutation_allowed":False}

def list_installs():
    with guarded():
        return {"apps":[_inspect(p,e) for p,e in sorted(_registry().items())],
                "pilot_supported_app_id":APP_ID,
                "scope":"approved_isolated_casaos_store_pilot",
                "production_mutation_allowed":False}

def action(op,app_id=None,project=None):
    if op not in ("install","start","stop","restart","uninstall"):
        raise AppError("unsupported_store_operation",400)
    with guarded():
        entries=_registry()
        if op=="install":
            if app_id!=APP_ID or project is not None:
                raise AppError("unsupported_casaos_store_install",400)
            if entries:
                raise AppError("staging_appstore_pilot_capacity",409)
            _catalog_image()
            # Never automatically pull arbitrary application images.
            _run("image","inspect",IMAGE,timeout=12)
            owner=registry()["owner"]
            project="osd-m1-store-"+secrets.token_hex(6)
            data=_data_dir(project)
            data.mkdir(mode=0o700,parents=True)
            ident=_run("run","--detach","--pull","never",
                "--name",project,"--network","none",
                "--cap-drop","ALL","--security-opt","no-new-privileges",
                "--memory","256m","--pids-limit","64",
                "--user","1000:1000",
                "--tmpfs","/tmp:rw,nosuid,noexec,size=16m",
                "--mount","type=bind,src="+str(data)+",dst="+DATA_TARGET,
                "--label","osd.m1.store=isolated-pilot",
                "--label","osd.m1.store.project="+project,
                "--label","osd.m1.store.owner="+owner,
                "--label","osd.m1.store.app="+APP_ID,
                IMAGE,timeout=60)
            if not CID_RE.fullmatch(ident):
                raise AppError("unexpected_staged_store_container_identity",503)
            entry={"id":ident,"owner":owner,"app_id":APP_ID}
            created=_inspect(project,entry)
            # docker run -d may succeed even if the app immediately exits.
            # Confirm it remains running before accepting it as installed.
            time.sleep(2)
            created=_inspect(project,entry)
            if not created["running"]:
                _run("rm","--force",ident)
                raise AppError("staging_store_pilot_failed_start_and_was_rolled_back",503)
            entries[project]=entry
            _save(entries)
            return {"operation":"installed","app":_inspect(project,entry)}
        if app_id is not None or not isinstance(project,str) or project not in entries:
            raise AppError("unknown_staging_store_install",404)
        entry=entries[project]
        current=_inspect(project,entry)
        if op=="start" and current["running"]:
            raise AppError("staged_store_already_running",409)
        if op=="stop" and not current["running"]:
            raise AppError("staged_store_already_stopped",409)
        if op=="restart" and not current["running"]:
            raise AppError("staged_store_not_running",409)
        ident=entry["id"]
        if op=="start":
            _run("start",ident)
        elif op=="stop":
            _run("stop","--time","2",ident)
        elif op=="restart":
            _run("restart","--time","2",ident)
        else:
            _run("rm","--force",ident)
            entries.pop(project)
            _save(entries)
            return {"operation":"uninstalled","project":project,
                    "stage_data_retained":True,"production_mutation_allowed":False}
        return {"operation":op,"app":_inspect(project,entry)}
