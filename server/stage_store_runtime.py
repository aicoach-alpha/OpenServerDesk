"""Isolated compiled CasaOS App Store multi-service runtime.

Only deploy compiler-created cached immutable images, no host ports/network,
no original user bind paths. Stage configuration image revisions can be
reverted. Rollback DOES NOT restore mutable application databases.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
from pathlib import Path
from stage_apps import AppError, guarded, registry as user_registry
from stage_store_compiler import compile_stage, STAGE

ROOT=Path(STAGE)
STATE=ROOT/"registry.json"
PROJECT=re.compile(r"osd-compiled-[0-9a-f]{12}\Z")
CID=re.compile(r"[0-9a-f]{64}\Z")
OWNER=re.compile(r"[0-9a-f]{32}\Z")
IMMUTABLE=re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_PROJECTS=2
PORT=re.compile(r"127\.0\.0\.1:(18[7-9][0-9]{2}|19[0-9]{3}):([0-9]{1,5})\Z")
# A dedicated internal bridge lets services communicate but has no external egress.
# A single app HTTP port may be published ONLY to local loopback.
def _pick_port(project):
    start=int(hashlib.sha256(project.encode()).hexdigest()[:6],16)%1280
    for offset in range(1280):
        port=18720+(start+offset)%1280
        with socket.socket() as sock:
            try: sock.bind(("127.0.0.1",port))
            except OSError: continue
        return port
    raise AppError("no_free_staging_loopback_port",409)

def _published_port(manifest):
    seen=[]
    for spec in manifest["services"].values():
        seen+=spec.get("ports",[])
    if not seen:return None
    if len(seen)!=1 or not isinstance(seen[0],str):
        raise AppError("unsafe_compiled_ports",403)
    match=PORT.fullmatch(seen[0])
    if not match:raise AppError("unsafe_compiled_ports",403)
    return int(match.group(1))

def _network_check(project,manifest,cfg,host,obj):
    if cfg.get("network_mode")=="none":
        if host.get("NetworkMode")!="none" or host.get("PortBindings"):
            raise AppError("compiled_stage_network_violation",403)
        return
    if cfg.get("networks")!=["isolated"] or manifest.get("networks")!={"isolated":{"internal":True}}:
        raise AppError("compiled_stage_network_definition_changed",403)
    network=project+"_isolated"
    if host.get("NetworkMode")!=network:
        raise AppError("compiled_stage_network_changed",403)
    try:
        info=json.loads(docker("network","inspect",network,timeout=20))[0]
    except (ValueError,TypeError,IndexError):
        raise AppError("compiled_stage_network_inspection_failed",503)
    labels=info.get("Labels") or {}
    if (info.get("Name")!=network or info.get("Internal") is not True or
            info.get("Driver")!="bridge" or
            labels.get("com.docker.compose.project")!=project or
            labels.get("com.docker.compose.network")!="isolated"):
        raise AppError("compiled_stage_foreign_network",403)
    declared=cfg.get("ports",[])
    portmap=host.get("PortBindings") or {}
    expected={}
    for port in declared:
        m=PORT.fullmatch(port)
        if not m or not 1<=int(m.group(2))<=65535:
            raise AppError("compiled_stage_unsafe_port",403)
        expected[str(int(m.group(2)))+"/tcp"]=[{"HostIp":"127.0.0.1","HostPort":m.group(1)}]
    if portmap!=expected:
        raise AppError("compiled_stage_port_mapping_changed",403)


def docker(*args, timeout=95):
    try:
        proc=subprocess.run(("docker",*args),capture_output=True,text=True,
                            check=False,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired):
        raise AppError("compiled_stage_docker_unavailable",503)
    if proc.returncode or len(proc.stdout)>200000:
        raise AppError("compiled_stage_docker_command_failed",503)
    return proc.stdout.strip()

def _root():
    if ROOT.is_symlink():
        raise AppError("unsafe_compiled_store_root",503)
    if not ROOT.exists():ROOT.mkdir(mode=0o700,parents=True)
    if not ROOT.is_dir() or ROOT.stat().st_mode & 0o077:
        raise AppError("unsafe_compiled_store_root",503)
    return ROOT

def _file(path):
    if path.is_symlink():
        raise AppError("unsafe_compiled_stage_file",503)
    return path

def _atomic(path,data):
    tmp=path.parent/(".compiled-"+secrets.token_hex(8))
    try:
        with tmp.open("x") as handle:
            json.dump(data,handle,sort_keys=True,indent=2)
            handle.flush();os.fsync(handle.fileno())
        tmp.chmod(0o600)
        os.replace(tmp,path)
        fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:tmp.unlink(missing_ok=True)

def _read(path,default):
    _file(path)
    if not path.is_file():return default
    if path.stat().st_size>90000:
        raise AppError("compiled_stage_record_too_large",503)
    try:return json.loads(path.read_text())
    except (OSError,ValueError):
        raise AppError("compiled_stage_record_invalid",503)

def _folder(project):
    if not isinstance(project,str) or not PROJECT.fullmatch(project):
        raise AppError("invalid_compiled_project",400)
    return _root()/project

def _projects():
    values=_read(STATE,{})
    if not isinstance(values,dict) or len(values)>MAX_PROJECTS:
        raise AppError("compiled_stage_registry_invalid",503)
    for key,item in values.items():
        if (not PROJECT.fullmatch(key) or not isinstance(item,dict)
            or set(item)!={"app_id","owner","revision"} or
            not isinstance(item["app_id"],str) or
            not isinstance(item["owner"],str) or
            not OWNER.fullmatch(item["owner"]) or
            type(item["revision"]) is not int or not 1<=item["revision"]<=500):
            raise AppError("compiled_stage_registry_invalid",503)
    return values

def _validate(project,manifest,owner):
    if not isinstance(manifest,dict) or set(manifest) not in (
        {"name","services"},{"name","services","networks"}) or manifest["name"]!=project:
        raise AppError("invalid_compiled_manifest",403)
    if "networks" in manifest and manifest["networks"]!={"isolated":{"internal":True}}:
        raise AppError("unsafe_compiled_networks",403)
    services=manifest["services"]
    if not isinstance(services,dict) or not 1<=len(services)<=6:
        raise AppError("invalid_compiled_services",403)
    base=_folder(project)
    if base.is_symlink() or not base.is_dir():
        raise AppError("unsafe_compiled_stage_directory",403)
    used=[]
    public=[]
    for name,cfg in sorted(services.items()):
        if not isinstance(name,str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_.-]{0,35}",name):
            raise AppError("invalid_compiled_service",403)
        if not isinstance(cfg,dict) or not IMMUTABLE.fullmatch(str(cfg.get("image",""))):
            raise AppError("invalid_compiled_image",403)
        expected={"osd.m1.compiled":"staging-only",
                  "osd.m1.compiled.project":project,
                  "osd.m1.compiled.service":name,
                  "osd.m1.compiled.app":cfg.get("labels",{}).get("osd.m1.compiled.app"),
                  "osd.m1.compiled.owner":owner}
        network_ok=(cfg.get("network_mode")=="none" and "networks" not in manifest and not cfg.get("networks"))
        network_ok=network_ok or (cfg.get("networks")==["isolated"] and
            "network_mode" not in cfg and "networks" in manifest)
        if (not network_ok or cfg.get("user")!="1000:1000"
            or cfg.get("pull_policy")!="never" or cfg.get("cap_drop")!=["ALL"]
            or cfg.get("security_opt")!=["no-new-privileges:true"]
            or cfg.get("restart")!="no" or cfg.get("labels")!=expected
            or cfg.get("privileged")
            or cfg.get("environment") or cfg.get("env_file")
            or cfg.get("devices") or cfg.get("build")):
            raise AppError("unsafe_compiled_service_settings",403)
        ports=cfg.get("ports",[])
        if not isinstance(ports,list) or len(ports)>1 or (ports and
           ("networks" not in manifest or not isinstance(ports[0],str) or
            not PORT.fullmatch(ports[0]) or
            not 1<=int(PORT.fullmatch(ports[0]).group(2))<=65535)):
            raise AppError("unsafe_compiled_ports",403)
        public.extend(ports)
        mounts=cfg.get("volumes",[])
        if not isinstance(mounts,list) or len(mounts)>5:
            raise AppError("unsafe_compiled_volume_count",403)
        for mount in mounts:
            if not isinstance(mount,dict) or set(mount)!={"type","source","target","bind"}:
                raise AppError("unsafe_compiled_stage_mount",403)
            src=Path(mount["source"])
            if (mount["type"]!="bind" or mount["bind"]!={"create_host_path":False}
                or src not in [base/name/("volume-"+str(i)) for i in range(5)]
                or not src.is_dir() or src.is_symlink()
                or src.stat().st_dev!=ROOT.stat().st_dev):
                raise AppError("unsafe_compiled_stage_volume",403)
            used.append(str(src))
    if len(used)!=len(set(used)):
        raise AppError("duplicate_compiled_stage_volume",403)
    if len(public)>1:
        raise AppError("too_many_compiled_public_ports",403)

def _compose_path(project):
    return _file(_folder(project)/"compose.json")

def _owned(project,manifest,owner):
    _validate(project,manifest,owner)
    raw=docker("ps","--all","--quiet","--no-trunc",
               "--filter","label=com.docker.compose.project="+project)
    ids=[x for x in raw.splitlines() if x]
    if len(ids)!=len(manifest["services"]) or len(set(ids))!=len(ids) or any(not CID.fullmatch(x) for x in ids):
        raise AppError("compiled_container_set_changed",403)
    seen={}
    for ident in ids:
        try:
            obj=json.loads(docker("inspect","--type","container",ident,timeout=25))[0]
        except (ValueError,KeyError,IndexError,TypeError):
            raise AppError("compiled_container_inspection_failed",503)
        cfg=obj.get("Config") or {}
        host=obj.get("HostConfig") or {}
        labels=cfg.get("Labels") or {}
        name=labels.get("com.docker.compose.service")
        spec=manifest["services"].get(name)
        if not isinstance(spec,dict) or name in seen:
            raise AppError("compiled_service_identity_mismatch",403)
        expected=spec["labels"]
        mounts=obj.get("Mounts") or []
        source_pairs={(x.get("Source"),x.get("Destination")) for x in mounts}
        expected_pairs={(x["source"],x["target"]) for x in spec["volumes"]}
        if (obj.get("Id")!=ident
            or cfg.get("Image")!=spec["image"]
            or cfg.get("User")!="1000:1000"
            or any(labels.get(k)!=v for k,v in expected.items())
            or labels.get("com.docker.compose.project")!=project
            or host.get("Privileged") is not False
            or source_pairs!=expected_pairs
            or any(x.get("Type")!="bind" for x in mounts)):
            raise AppError("compiled_container_provenance_violation",403)
        _network_check(project,manifest,spec,host,obj)
        seen[name]={"name":name,"id":ident,"running":bool((obj.get("State") or {}).get("Running"))}
    return seen

def _manifest(project,app_id,owner,raw):
    if not isinstance(raw,dict) or not isinstance(raw.get("services"),dict):
        raise AppError("invalid_compiled_manifest",403)
    output=json.loads(json.dumps(raw))
    for name,spec in output["services"].items():
        spec["labels"]["osd.m1.compiled.owner"]=owner
    return output

def _prepare_volumes(project,raw):
    folder=_folder(project)
    for name,spec in raw["services"].items():
        for mount in spec.get("volumes",[]):
            path=Path(mount["source"])
            if path.parent!=folder/name or not path.name.startswith("volume-"):
                raise AppError("invalid_stage_mount_source",403)
            path.mkdir(mode=0o700,parents=True)
    # even zero-volume services need stage folder
    for name in raw["services"]:
        (folder/name).mkdir(mode=0o700,parents=True)

def _current(project,entry):
    folder=_folder(project)
    if folder.is_symlink() or not folder.is_dir():
        raise AppError("compiled_stage_project_dir_invalid",403)
    manifest=_read(_compose_path(project),None)
    if not isinstance(manifest,dict):
        raise AppError("compiled_stage_manifest_missing",503)
    services=_owned(project,manifest,entry["owner"])
    return manifest,services

def _up(project):
    docker("compose","--project-name",project,"--file",str(_compose_path(project)),
           "up","--detach","--no-build","--pull","never",timeout=95)

def _verify_partial(project,manifest,owner):
    """Before crash recovery, reject foreign or relabeled containers.

    Does not require the complete original set: a failed operation may
    legitimately have created or deleted only some stage containers.
    """
    _validate(project,manifest,owner)
    ids=docker("ps","--all","--quiet","--no-trunc",
               "--filter","label=com.docker.compose.project="+project).splitlines()
    if len(ids)>len(manifest["services"]) or len(set(ids))!=len(ids):
        raise AppError("unexpected_compiled_recovery_containers",403)
    names=set()
    for ident in ids:
        if not CID.fullmatch(ident):
            raise AppError("invalid_compiled_recovery_container",403)
        try:
            obj=json.loads(docker("inspect","--type","container",ident))[0]
        except (ValueError,TypeError,IndexError,KeyError):
            raise AppError("invalid_compiled_recovery_inspection",403)
        cfg=obj.get("Config") or {}
        host=obj.get("HostConfig") or {}
        labels=cfg.get("Labels") or {}
        name=labels.get("com.docker.compose.service")
        spec=manifest["services"].get(name)
        if not isinstance(spec,dict) or name in names:
            raise AppError("unexpected_compiled_recovery_service",403)
        names.add(name)
        mounts=obj.get("Mounts") or []
        expected={(v["source"],v["target"]) for v in spec["volumes"]}
        if (obj.get("Id")!=ident
            or any(labels.get(k)!=v for k,v in spec["labels"].items())
            or labels.get("com.docker.compose.project")!=project
            or host.get("Privileged") is not False
            or {(x.get("Source"),x.get("Destination")) for x in mounts}!=expected):
            raise AppError("foreign_compiled_recovery_container",403)
        _network_check(project,manifest,spec,host,obj)
    return ids


def _down_owned(project,manifest,owner):
    ids=_owned(project,manifest,owner)
    for item in ids.values():
        # Keep actions constrained to verified full IDs.
        docker("rm","--force",item["id"],timeout=30)
    if "networks" in manifest:
        network=project+"_isolated"
        try: info=json.loads(docker("network","inspect",network))[0]
        except (ValueError,IndexError,TypeError):
            raise AppError("compiled_stage_network_cleanup_unverified",503)
        labels=info.get("Labels") or {}
        if (info.get("Name")!=network or info.get("Internal") is not True or
                labels.get("com.docker.compose.project")!=project or
                labels.get("com.docker.compose.network")!="isolated" or
                info.get("Containers")):
            raise AppError("compiled_stage_network_cleanup_unverified",403)
        docker("network","rm",network,timeout=30)

def _summary(project,entry):
    manifest,services=_current(project,entry)
    return {"project":project,"app_id":entry["app_id"],
            "revision":entry["revision"],
            "services":[{"name":s["name"],"running":s["running"]}
                        for s in sorted(services.values(),key=lambda x:x["name"])],
            "all_running":all(x["running"] for x in services.values()),
            "image_configuration_rollback":True,
            "application_data_rollback":False,
            "web_url":("http://127.0.0.1:"+str(_published_port(manifest))
                       if _published_port(manifest) is not None else None),
            "production_mutation_allowed":False}

def listing():
    with guarded():
        root=_root()
        pending=[]
        for child in root.iterdir():
            if PROJECT.fullmatch(child.name) and not child.is_symlink():
                j=child/"pending.json"
                if j.is_file() or j.is_symlink():
                    pending.append(child.name)
        values=_projects()
        return {"apps":[_summary(p,e) for p,e in sorted(values.items())
                        if p not in pending],
                "pending_recovery":sorted(pending),
                "scope":"isolated_compiled_appstore_runtime",
                "application_data_rollback":False,
                "migration_allowed":False,"production_mutation_allowed":False}

def operation(action,app_id=None,project=None):
    if action not in ("install","start","stop","restart","uninstall","update","rollback","recover"):
        raise AppError("invalid_compiled_stage_action",400)
    with guarded():
        values=_projects()
        if action=="install":
            if project is not None or len(values)>=MAX_PROJECTS:
                raise AppError("compiled_stage_capacity",409)
            project="osd-compiled-"+secrets.token_hex(6)
            if docker("ps","--all","--quiet","--no-trunc",
                      "--filter","label=com.docker.compose.project="+project):
                raise AppError("compiled_stage_project_name_collision",409)
            # Refuse a pre-existing network of the same generated name.
            try:
                existing=docker("network","ls","--quiet","--filter",
                                "name=^"+project+"_isolated$")
            except AppError:
                raise
            if existing:
                raise AppError("staging_network_name_collision",409)
            raw=compile_stage(project,app_id,host_port=_pick_port(project))
            owner=user_registry()["owner"]
            folder=_folder(project)
            folder.mkdir(mode=0o700)
            _prepare_volumes(project,raw)
            manifest=_manifest(project,app_id,owner,raw)
            _validate(project,manifest,owner)
            _atomic(_compose_path(project),manifest)
            # If this fails, a stage-only project may need operator review.
            # We record an explicit fail-closed recovery marker.
            journal=_file(folder/"pending.json")
            _atomic(journal,{"operation":"install","app_id":app_id,"owner":owner})
            try:
                _up(project)
                _owned(project,manifest,owner)
                values[project]={"app_id":app_id,"owner":owner,"revision":1}
                _atomic(STATE,values)
                journal.unlink()
            except Exception:
                raise
            return {"operation":"installed","app":_summary(project,values[project])}
        if action=="recover":
            if app_id is not None or not isinstance(project,str) or not PROJECT.fullmatch(project):
                raise AppError("invalid_compiled_recovery_request",400)
            folder=_folder(project)
            journal=_file(folder/"pending.json")
            if not journal.is_file():
                raise AppError("no_pending_compiled_stage_operation",404)
            state=_read(journal,None)
            if not isinstance(state,dict) or state.get("operation") not in ("install","uninstall","update","rollback"):
                raise AppError("invalid_compiled_stage_recovery_journal",503)
            if state["operation"]=="install":
                owner=state.get("owner")
                if not isinstance(owner,str) or not OWNER.fullmatch(owner):
                    raise AppError("invalid_compiled_stage_owner",403)
                manifest=_read(_compose_path(project),None)
                if not isinstance(manifest,dict):
                    raise AppError("missing_compiled_install_manifest",503)
                _validate(project,manifest,owner)
                _verify_partial(project,manifest,owner)
                found=docker("ps","--all","--quiet","--no-trunc",
                             "--filter","label=com.docker.compose.project="+project)
                for ident in found.splitlines():
                    if ident:
                        docker("rm","--force",ident)
                if "networks" in manifest:
                    network=project+"_isolated"
                    found=docker("network","ls","--quiet","--filter","name=^"+network+"$")
                    if found:
                        try: info=json.loads(docker("network","inspect",network))[0]
                        except (TypeError,ValueError,IndexError):
                            raise AppError("compiled_stage_network_cleanup_unverified",503)
                        labels=info.get("Labels") or {}
                        if (info.get("Name")!=network or info.get("Internal") is not True or
                                labels.get("com.docker.compose.project")!=project or
                                labels.get("com.docker.compose.network")!="isolated" or
                                info.get("Containers")):
                            raise AppError("compiled_stage_network_cleanup_unverified",403)
                        docker("network","rm",network)
                values.pop(project,None)
                _atomic(STATE,values)
            else:
                old=state.get("old")
                entry=state.get("entry") if state["operation"]=="uninstall" else values.get(project)
                if not isinstance(entry,dict) or not isinstance(old,dict):
                    raise AppError("compiled_rollback_evidence_unavailable",503)
                owner=entry.get("owner")
                if not isinstance(owner,str) or not OWNER.fullmatch(owner):
                    raise AppError("invalid_compiled_stage_owner",403)
                _validate(project,old,owner)
                _verify_partial(project,old,owner)
                _atomic(_compose_path(project),old)
                _up(project)
                _owned(project,old,owner)
                if state["operation"]=="uninstall":
                    values[project]=entry
                else:
                    revision=state.get("revision")
                    if type(revision) is not int or revision<1:
                        raise AppError("invalid_compiled_restore_revision",503)
                    entry["revision"]=revision
                _atomic(STATE,values)
            journal.unlink()
            return {"operation":"recovered","project":project,
                    "scope":"isolated_compiled_stage_only",
                    "application_data_rollback":False,
                    "production_mutation_allowed":False}
        if not isinstance(project,str) or project not in values or app_id is not None:
            raise AppError("unknown_compiled_stage_project",404)
        entry=values[project]
        folder=_folder(project)
        journal=_file(folder/"pending.json")
        if journal.exists():
            raise AppError("compiled_stage_recovery_required",409)
        manifest,services=_current(project,entry)
        if action=="uninstall":
            _atomic(journal,{"operation":"uninstall","old":manifest,"entry":entry})
            _down_owned(project,manifest,entry["owner"])
            values.pop(project)
            _atomic(STATE,values)
            journal.unlink()
            return {"operation":"uninstalled","project":project,
                    "stage_data_retained":True,"production_mutation_allowed":False}
        if action in ("start","stop","restart"):
            for item in services.values():
                if action=="start" and not item["running"]:
                    docker("start",item["id"])
                if action=="stop" and item["running"]:
                    docker("stop","--time","2",item["id"])
                if action=="restart" and item["running"]:
                    docker("restart","--time","2",item["id"])
            return {"operation":action,"app":_summary(project,entry)}
        # Configuration/image rollback. Stage volumes are retained in-place;
        # mutable DB contents are NOT snapshotted or restored.
        previous=_file(folder/"previous.json")
        if action=="update":
            new_raw=compile_stage(project,entry["app_id"],
                                  host_port=_published_port(manifest))
            updated=_manifest(project,entry["app_id"],entry["owner"],new_raw)
            _validate(project,updated,entry["owner"])
            if updated==manifest:
                return {"operation":"no_change","app":_summary(project,entry)}
            if entry["revision"]>=500:
                raise AppError("compiled_stage_revision_limit",409)
            target=updated
        else:
            target=_read(previous,None)
            if target is None:
                raise AppError("no_previous_compiled_stage_image",409)
            _validate(project,target,entry["owner"])
        # Journal existing whole configuration before ANY Docker replace.
        _atomic(journal,{"operation":action,"old":manifest,
                         "revision":entry["revision"]})
        _atomic(_compose_path(project),target)
        try:
            _up(project)
            _owned(project,target,entry["owner"])
            _atomic(previous,manifest)
            entry["revision"]+=1
            _atomic(STATE,values)
            journal.unlink()
        except Exception:
            # Do not rewrite another app. Restore known original manifest and
            # recreate only this generated project; leave journal on failure.
            _atomic(_compose_path(project),manifest)
            try:
                _up(project)
                _owned(project,manifest,entry["owner"])
                journal.unlink()
            except Exception:
                raise AppError("compiled_stage_rollback_requires_recovery",503)
            raise AppError("compiled_stage_update_failed_original_restored",503)
        return {"operation":action,"app":_summary(project,entry)}
