"""Live, isolated multi-service Docker Compose topology manager.

User specifies SERVICE STRUCTURE ONLY, never image, mount path, ports,
commands, cap or network. Existing CasaOS workloads cannot be addressed.
Every action checks the immutable 64-char container ID, all stage owner
labels, read-only rootfs, staged data bind and absence of host ports.
"""
from __future__ import annotations
import json
import os
import re
import secrets
import subprocess
from pathlib import Path

from stage_apps import STAGE, AppError, guarded, registry
from stage_compose import _command

ROOT = STAGE / "topology-projects"
DATABASE = STAGE / "topology-registry.json"
NAME = re.compile(r"osd-m1-topology-[0-9a-f]{12}\Z")
SERVICE = re.compile(r"[a-z][a-z0-9_-]{0,30}\Z")
CID = re.compile(r"[0-9a-f]{64}\Z")
IMAGE = "busybox:latest"
MAX_PROJECTS = 3
MAX_SERVICES = 4
MOUNT = "/osd-config"


def validate(services):
    if not isinstance(services, list) or not 2 <= len(services) <= MAX_SERVICES:
        raise AppError("invalid_topology_service_count", 400)
    names = set()
    mapping = {}
    for item in services:
        if not isinstance(item, dict) or set(item) != {"name","depends_on"}:
            raise AppError("invalid_topology_service", 400)
        name = item["name"]
        deps = item["depends_on"]
        if (not isinstance(name, str) or not SERVICE.fullmatch(name)
                or name in names or not isinstance(deps, list) or len(deps) > MAX_SERVICES
                or any(not isinstance(x,str) or not SERVICE.fullmatch(x) for x in deps)
                or len(set(deps)) != len(deps)):
            raise AppError("invalid_topology_service", 400)
        names.add(name)
        mapping[name] = tuple(deps)
    if any(dep not in names for deps in mapping.values() for dep in deps):
        raise AppError("unknown_topology_dependency", 400)
    visited=set()
    visiting=set()
    def walk(name):
        if name in visiting:
            raise AppError("cyclic_topology_dependency",400)
        if name in visited:
            return
        visiting.add(name)
        for dep in mapping[name]:
            walk(dep)
        visiting.remove(name)
        visited.add(name)
    for name in sorted(names):
        walk(name)
    return {name:list(mapping[name]) for name in sorted(names)}


def _root():
    if ROOT.is_symlink():
        raise AppError("unsafe_topology_root",503)
    if not ROOT.exists():
        ROOT.mkdir(mode=0o700)
    if not ROOT.is_dir() or ROOT.stat().st_mode & 0o077:
        raise AppError("unsafe_topology_root",503)
    return ROOT


def _folder(project):
    if not isinstance(project, str) or not NAME.fullmatch(project):
        raise AppError("invalid_topology_project",400)
    return _root() / project


def _registry():
    if DATABASE.is_symlink():
        raise AppError("unsafe_topology_registry",503)
    if not DATABASE.is_file():
        return {}
    try:
        record=json.loads(DATABASE.read_text())
        if not isinstance(record,dict) or len(record)>MAX_PROJECTS:
            raise ValueError("bad registry")
        for project, entry in record.items():
            if (not NAME.fullmatch(project) or not isinstance(entry,dict)
                    or set(entry)!={"owner","services","containers"}
                    or not re.fullmatch("[0-9a-f]{32}",entry["owner"])):
                raise ValueError("bad entry")
            mapping=validate(entry["services"])
            if (set(entry["containers"])!=set(mapping)
                    or any(not isinstance(cid,str) or not CID.fullmatch(cid)
                           for cid in entry["containers"].values())):
                raise ValueError("bad service IDs")
        return record
    except (OSError,ValueError,TypeError,KeyError,AppError):
        raise AppError("topology_registry_corrupt",503)


def _write(reg):
    temp=STAGE / (".topology-registry-"+secrets.token_hex(8))
    try:
        with temp.open("x") as file:
            json.dump(reg,file,sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
        temp.chmod(0o600)
        os.replace(temp,DATABASE)
        fd=os.open(STAGE,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:
        temp.unlink(missing_ok=True)


def _compose(project,owner,mapping,data):
    services={}
    for name, deps in sorted(mapping.items()):
        cfg={
            "image":IMAGE, "pull_policy":"never",
            "command":["sleep","86400"],
            "network_mode":"none",
            "read_only":True,
            "user":"1000:1000",
            "cap_drop":["ALL"],
            "security_opt":["no-new-privileges:true"],
            "pids_limit":16, "mem_limit":"32m", "restart":"no",
            "labels":{
                "osd.m1.topology":"stage-only",
                "osd.m1.topology.owner":owner,
                "osd.m1.topology.project":project,
                "osd.m1.topology.service":name,
            },
            "volumes":[{
                "type":"bind","source":str(data),
                "target":MOUNT,"read_only":True,
                "bind":{"create_host_path":False},
            }],
        }
        if deps:cfg["depends_on"]=deps
        services[name]=cfg
    return json.dumps({"name":project,"services":services},sort_keys=True,indent=2)+"\n"


def _inspect_one(project,owner,name,ident,data):
    if not CID.fullmatch(ident):
        raise AppError("invalid_topology_container",403)
    try:
        obj=json.loads(_command("docker","inspect","--type","container",ident,timeout=20))[0]
    except (ValueError,IndexError,KeyError,TypeError):
        raise AppError("topology_container_inspection_failed",503)
    cfg=obj.get("Config") or {}
    host=obj.get("HostConfig") or {}
    labels=cfg.get("Labels") or {}
    mounts=obj.get("Mounts") or []
    if (obj.get("Id")!=ident
            or labels.get("com.docker.compose.project")!=project
            or labels.get("com.docker.compose.service")!=name
            or labels.get("osd.m1.topology")!="stage-only"
            or labels.get("osd.m1.topology.owner")!=owner
            or labels.get("osd.m1.topology.project")!=project
            or labels.get("osd.m1.topology.service")!=name
            or cfg.get("Image")!=IMAGE or cfg.get("User")!="1000:1000"
            or host.get("Privileged") is not False
            or host.get("NetworkMode")!="none"
            or host.get("ReadonlyRootfs") is not True
            or host.get("PortBindings") or host.get("Binds")
            or len(mounts)!=1
            or mounts[0].get("Type")!="bind"
            or mounts[0].get("Source")!=str(data)
            or mounts[0].get("Destination")!=MOUNT
            or mounts[0].get("RW") is not False):
        raise AppError("topology_container_provenance_violation",403)
    state=obj.get("State") or {}
    return {"name":name,"id":ident[:12],"running":bool(state.get("Running")),
            "isolated":True}


def _verified(project,entry):
    folder=_folder(project)
    data=folder/"data"
    config=folder/"compose.json"
    if (folder.is_symlink() or data.is_symlink() or config.is_symlink()
            or not data.is_dir() or not config.is_file()):
        raise AppError("topology_project_files_invalid",503)
    mapping=validate(entry["services"])
    if config.read_text()!=_compose(project,entry["owner"],mapping,data):
        raise AppError("topology_configuration_changed",403)
    results=[]
    for name,ident in sorted(entry["containers"].items()):
        results.append(_inspect_one(project,entry["owner"],name,ident,data))
    # Reject extras which could be acted upon by Compose project name.
    actual=_command("docker","ps","--all","--quiet","--no-trunc",
                    "--filter","label=com.docker.compose.project="+project)
    if set(actual.splitlines())!=set(entry["containers"].values()):
        raise AppError("unexpected_topology_container_count",403)
    return {"project":project,"services":results,"running":all(x["running"] for x in results),
            "isolated":True,"production_mutation_allowed":False}


def list_topologies():
    with guarded():
        return {"topologies":[_verified(project,entry)
                              for project,entry in sorted(_registry().items())],
                "scope":"isolated_multiservice_topology_only",
                "production_mutation_allowed":False}


def action(op,project=None,services=None):
    if op not in ("install","start","stop","restart","uninstall"):
        raise AppError("invalid_topology_operation",400)
    with guarded():
        current=_registry()
        if op=="install":
            if project is not None or len(current)>=MAX_PROJECTS:
                raise AppError("topology_capacity_or_bad_project",409)
            mapping=validate(services)
            owner=registry()["owner"]
            project="osd-m1-topology-"+secrets.token_hex(6)
            folder=_folder(project)
            folder.mkdir(mode=0o700)
            data=folder/"data"
            data.mkdir(mode=0o700)
            (data/"readme.txt").write_text("OpenServerDesk isolated topology\n")
            config=folder/"compose.json"
            config.write_text(_compose(project,owner,mapping,data))
            try:
                _command("docker","compose","--project-name",project,
                         "--file",str(config),"up","--detach",
                         "--no-build","--pull","never",timeout=95)
                ids=_command("docker","ps","--all","--quiet","--no-trunc",
                             "--filter","label=com.docker.compose.project="+project).splitlines()
                if len(ids)!=len(mapping) or any(not CID.fullmatch(x) for x in ids):
                    raise AppError("unexpected_topology_container_set",503)
                containers={}
                for ident in ids:
                    raw=json.loads(_command("docker","inspect","--type","container",ident))[0]
                    name=(raw.get("Config") or {}).get("Labels",{}).get("com.docker.compose.service")
                    if name not in mapping or name in containers:
                        raise AppError("unexpected_topology_service_identity",403)
                    _inspect_one(project,owner,name,ident,data)
                    containers[name]=ident
                entry={"owner":owner,"services":[{"name":name,"depends_on":deps}
                                                    for name,deps in mapping.items()],
                       "containers":containers}
                _verified(project,entry)
                current[project]=entry
                _write(current)
                return {"operation":"installed","topology":_verified(project,entry)}
            except Exception:
                # Never delete on project-name alone. Unknown app identities
                # are left unchanged for operator review, not force removed.
                # Do not remove original production apps or other workloads.
                raise
        if (not isinstance(project,str) or project not in current or services is not None):
            raise AppError("unknown_topology_project",404)
        entry=current[project]
        before=_verified(project,entry)
        if op=="start" and all(x["running"] for x in before["services"]):
            raise AppError("topology_already_running",409)
        if op=="stop" and not any(x["running"] for x in before["services"]):
            raise AppError("topology_already_stopped",409)
        if op=="uninstall":
            remaining=set(entry["containers"].values())
            for service in before["services"]:
                ident=entry["containers"][service["name"]]
                # Uninstalling one verified service invalidates the full
                # project check. Reverify exact remaining IDs and the
                # individual immutable service identity before every rm.
                current_ids=set(_command(
                    "docker","ps","--all","--quiet","--no-trunc",
                    "--filter","label=com.docker.compose.project="+project).splitlines())
                if current_ids!=remaining:
                    raise AppError("topology_project_changed_during_uninstall",403)
                _inspect_one(project,entry["owner"],service["name"],ident,
                             _folder(project)/"data")
                _command("docker","rm","--force",ident)
                remaining.remove(ident)
            current.pop(project)
            _write(current)
            return {"operation":"uninstalled","project":project,
                    "stage_data_retained":True,"production_mutation_allowed":False}
        for service in before["services"]:
            ident=entry["containers"][service["name"]]
            # Re-verify ALL immutable provenance before EACH mutating command.
            _verified(project,entry)
            if op=="start" and not service["running"]:
                _command("docker","start",ident)
            elif op=="stop" and service["running"]:
                _command("docker","stop","--time","2",ident)
            elif op=="restart" and service["running"]:
                _command("docker","restart","--time","2",ident)
        return {"operation":op,"topology":_verified(project,entry)}
