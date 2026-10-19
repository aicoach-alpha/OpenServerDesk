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
import time
from pathlib import Path
from stage_apps import AppError, guarded, registry as user_registry
from stage_store_compiler import compile_stage, prepare_images, STAGE
from stage_store_data import (
    listing as data_listing, checkpoint as data_checkpoint,
    restore as data_restore, recover as data_recover,
    _validate_snapshot as _data_validate,
    _save as _data_save,
    _apply as _data_apply)

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

def _network_contract(manifest):
    networks=manifest.get("networks")
    if networks=={"isolated":{"internal":True}}:
        return "isolated",True
    if networks=={"egress":{"driver":"bridge","internal":False}}:
        services=manifest.get("services",{})
        if (not isinstance(services,dict) or set(services)!={"myspeed"}
                or (services["myspeed"].get("labels") or {}).get(
                    "osd.m1.compiled.app")!="default:MySpeed"):
            raise AppError("stage_outbound_policy_denied",403)
        return "egress",False
    raise AppError("compiled_stage_network_definition_changed",403)

def _network_check(project,manifest,cfg,host,obj):
    if cfg.get("network_mode")=="none":
        if host.get("NetworkMode")!="none" or host.get("PortBindings"):
            raise AppError("compiled_stage_network_violation",403)
        return
    name,internal=_network_contract(manifest)
    if cfg.get("networks")!=[name]:
        raise AppError("compiled_stage_network_definition_changed",403)
    network=project+"_"+name
    if host.get("NetworkMode")!=network:
        raise AppError("compiled_stage_network_changed",403)
    try:
        info=json.loads(docker("network","inspect",network,timeout=20))[0]
    except (ValueError,TypeError,IndexError):
        raise AppError("compiled_stage_network_inspection_failed",503)
    labels=info.get("Labels") or {}
    if (info.get("Name")!=network or info.get("Internal") is not internal or
            info.get("Driver")!="bridge" or
            labels.get("com.docker.compose.project")!=project or
            labels.get("com.docker.compose.network")!=name):
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


def _tcp_ready(port):
    if port is None:return True
    try:
        with socket.create_connection(("127.0.0.1",port),timeout=0.5):
            return True
    except OSError:
        return False

def _confirm_ready(project,manifest,owner,grace_seconds=11):
    """Reject containers that only briefly run immediately after docker up.

    Check only exact verified stage-owned container IDs and loopback web port.
    """
    if not isinstance(grace_seconds,(int,float)) or not 1<=grace_seconds<=30:
        raise AppError("invalid_stage_startup_grace",400)
    deadline=time.monotonic()+grace_seconds
    port=_published_port(manifest)
    while True:
        services=_owned(project,manifest,owner)
        running=bool(services) and all(x["running"] for x in services.values())
        reachable=running and _tcp_ready(port)
        now=time.monotonic()
        if now>=deadline:
            if reachable:
                return {"running":True,"web_reachable":port is None or reachable,
                        "checked_services":len(services)}
            raise AppError("compiled_stage_application_failed_readiness",503)
        if any(x.get("status")=="exited" for x in services.values()):
            raise AppError("compiled_stage_application_exited_during_start",503)
        time.sleep(min(1.5,max(0,deadline-now)))

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
    network=None
    if "networks" in manifest:
        network,internal=_network_contract(manifest)
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
        network_ok=network_ok or (network is not None
            and cfg.get("networks")==[network] and "network_mode" not in cfg)
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
        state=obj.get("State") or {}
        seen[name]={"name":name,"id":ident,"running":bool(state.get("Running")),
                    "status":state.get("Status","unknown"),
                    "exit_code":state.get("ExitCode") if state.get("Status")=="exited" else None,
                    "oom_killed":state.get("OOMKilled") is True}
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
            if (path.is_symlink() or not path.is_dir() or
                path.stat().st_dev != ROOT.stat().st_dev):
                raise AppError("unsafe_stage_volume_boundary",403)
            # New isolated bind roots belong to the fixed container user.
            # Project/backup parents remain root-owned and inaccessible.
            os.chown(path,1000,1000)
            path.chmod(0o700)
    # Service directory may already have been created by its volumes.
    # Without exist_ok, every non-empty volume declaration fails installation.
    for name in raw["services"]:
        service_dir=folder/name
        service_dir.mkdir(mode=0o700,parents=True,exist_ok=True)
        if (service_dir.is_symlink() or not service_dir.is_dir() or
            service_dir.stat().st_dev!=ROOT.stat().st_dev):
            raise AppError("unsafe_stage_service_directory",403)

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
        name,internal=_network_contract(manifest)
        network=project+"_"+name
        try: info=json.loads(docker("network","inspect",network))[0]
        except (ValueError,IndexError,TypeError):
            raise AppError("compiled_stage_network_cleanup_unverified",503)
        labels=info.get("Labels") or {}
        if (info.get("Name")!=network or info.get("Internal") is not internal or
                labels.get("com.docker.compose.project")!=project or
                labels.get("com.docker.compose.network")!=name or
                info.get("Containers")):
            raise AppError("compiled_stage_network_cleanup_unverified",403)
        docker("network","rm",network,timeout=30)

def _summary(project,entry):
    manifest,services=_current(project,entry)
    return {"project":project,"app_id":entry["app_id"],
            "revision":entry["revision"],
            "services":[{"name":s["name"],"running":s["running"],
                         "status":s["status"],"exit_code":s["exit_code"],
                         "oom_killed":s["oom_killed"]}
                        for s in sorted(services.values(),key=lambda x:x["name"])],
            "all_running":all(x["running"] for x in services.values()),
            "outbound_network_pilot":_network_contract(manifest)[0]=="egress" if "networks" in manifest else False,
            "image_configuration_rollback":True,
            "application_data_rollback":False,
            "manual_stage_volume_backup_restore":True,
            "data_checkpoints":data_listing(project,manifest),
            "data_recovery_pending":(_folder(project)/"data-restore-pending.json").exists(),
            "online_data_recovery_pending":_online_file(project).exists(),
            "web_url":("http://127.0.0.1:"+str(_published_port(manifest))
                       if _published_port(manifest) is not None else None),
            "production_mutation_allowed":False}

def _online_file(project):
    return _file(_folder(project)/"online-data-pending.json")

def _stop_for_online(services):
    for s in services.values():
        if s["running"]:
            docker("stop","--time","3",s["id"])

def _resume_online(project,manifest,owner,running):
    """Resume only services that were running before the online operation."""
    current=_owned(project,manifest,owner)
    if set(running)!=set(current):
        raise AppError("stage_online_service_layout_changed",503)
    for name,s in current.items():
        if name in running and not s["running"]:
            docker("start",s["id"])
    current=_owned(project,manifest,owner)
    if any(current[name]["running"]!=(name in running) for name in current):
        raise AppError("stage_online_service_restart_mismatch",503)
    if len(running)==len(current) and running:
        _confirm_ready(project,manifest,owner)

def _online_recover(project,manifest,entry):
    path=_online_file(project)
    record=_read(path,None)
    if not isinstance(record,dict) or record.get("version")!=1 or record.get("operation") not in (
        "backup-online","restore-online"):
        raise AppError("no_stage_online_data_recovery",404)
    running=record.get("running")
    if (not isinstance(running,list) or len(running)!=len(set(running))
            or not all(isinstance(x,str) and x in manifest["services"] for x in running)):
        raise AppError("invalid_stage_online_recovery_journal",503)
    _stop_for_online(_owned(project,manifest,entry["owner"]))
    current=_owned(project,manifest,entry["owner"])
    if record["operation"]=="restore-online":
        undo=record.get("undo")
        if undo is not None:
            _data_apply(project,manifest,undo)
    _resume_online(project,manifest,entry["owner"],set(running))
    path.unlink()
    return {"operation":"recovered_online_data","restored_old_data":(
                record["operation"]=="restore-online" and record.get("undo") is not None),
            "production_mutation_allowed":False,"app":_summary(project,entry)}

def _online_data(project,manifest,entry,services,action,checkpoint):
    path=_online_file(project)
    if path.exists() or path.is_symlink():
        raise AppError("stage_online_data_recovery_required",409)
    running=sorted(name for name,s in services.items() if s["running"])
    if action=="restore-online":
        _data_validate(project,manifest,checkpoint)
    elif checkpoint is not None:
        raise AppError("invalid_online_checkpoint_request",400)
    record={"version":1,"operation":action,"running":running,"undo":None}
    # Journal first; a crash during stop/checkpoint can be recovered safely.
    _atomic(path,record)
    try:
        _stop_for_online(services)
        current=_owned(project,manifest,entry["owner"])
        if any(x["running"] for x in current.values()):
            raise AppError("stage_online_stop_incomplete",503)
        if action=="backup-online":
            saved=data_checkpoint(project,manifest,current)
            result={"operation":"backed_up_online","checkpoint":saved["checkpoint"],
                    "sqlite_files_verified":saved["sqlite_files_verified"]}
        else:
            # Preserve exact pre-restore bytes BEFORE mutating anything.
            # The journal pins this undo checkpoint durably.
            record["undo"]=_data_save(project,manifest)
            _atomic(path,record)
            checked=_data_apply(project,manifest,checkpoint)
            result={"operation":"restored_online","checkpoint":checkpoint,
                    "undo":record["undo"],"sqlite_files_verified":checked}
        _resume_online(project,manifest,entry["owner"],set(running))
        path.unlink()
        result.update({"production_mutation_allowed":False,"app":_summary(project,entry)})
        return result
    except Exception as err:
        # Leave a durable journal. No blind automatic retry after a crash.
        raise AppError("stage_online_data_requires_recovery",503) from err

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

def operation(action,app_id=None,project=None,checkpoint=None):
    if action not in ("prepare","install","start","stop","restart","uninstall","update","rollback","recover",
                      "checkpoint","restore-data","recover-data",
                      "backup-online","restore-online","recover-online"):
        raise AppError("invalid_compiled_stage_action",400)
    with guarded():
        values=_projects()
        if action=="prepare":
            if checkpoint is not None or project is not None or not isinstance(app_id,str):
                raise AppError("invalid_compiled_image_prepare_request",400)
            return prepare_images(app_id)
        if action=="install":
            if checkpoint is not None or project is not None or len(values)>=MAX_PROJECTS:
                raise AppError("compiled_stage_capacity",409)
            project="osd-compiled-"+secrets.token_hex(6)
            if docker("ps","--all","--quiet","--no-trunc",
                      "--filter","label=com.docker.compose.project="+project):
                raise AppError("compiled_stage_project_name_collision",409)
            # Refuse ALL pre-existing network names within this generated namespace.
            for network_name in ("isolated","egress"):
                existing=docker("network","ls","--quiet","--filter",
                                "name=^"+project+"_"+network_name+"$")
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
                _confirm_ready(project,manifest,owner)
                values[project]={"app_id":app_id,"owner":owner,"revision":1}
                _atomic(STATE,values)
                journal.unlink()
            except Exception:
                raise
            return {"operation":"installed","app":_summary(project,values[project])}
        if action=="recover":
            if checkpoint is not None or app_id is not None or not isinstance(project,str) or not PROJECT.fullmatch(project):
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
                    name,internal=_network_contract(manifest)
                    network=project+"_"+name
                    found=docker("network","ls","--quiet","--filter","name=^"+network+"$")
                    if found:
                        try: info=json.loads(docker("network","inspect",network))[0]
                        except (TypeError,ValueError,IndexError):
                            raise AppError("compiled_stage_network_cleanup_unverified",503)
                        labels=info.get("Labels") or {}
                        if (info.get("Name")!=network or info.get("Internal") is not internal or
                                labels.get("com.docker.compose.project")!=project or
                                labels.get("com.docker.compose.network")!=name or
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
        if (_online_file(project).exists() or _online_file(project).is_symlink()) and action!="recover-online":
            raise AppError("stage_online_data_recovery_required",409)
        manifest,services=_current(project,entry)
        data_pending=folder/"data-restore-pending.json"
        if data_pending.exists() or data_pending.is_symlink():
            if action!="recover-data":
                raise AppError("stage_data_recovery_required",409)
        if action=="recover-online":
            if checkpoint is not None:
                raise AppError("invalid_online_recovery_request",400)
            return _online_recover(project,manifest,entry)
        if action in ("backup-online","restore-online"):
            return _online_data(project,manifest,entry,services,action,checkpoint)
        if action=="checkpoint":
            if checkpoint is not None:
                raise AppError("invalid_data_checkpoint_request",400)
            return data_checkpoint(project,manifest,services)
        if action=="restore-data":
            return data_restore(project,manifest,services,checkpoint)
        if action=="recover-data":
            if checkpoint is not None:
                raise AppError("invalid_data_recovery_request",400)
            return data_recover(project,manifest,services)
        if checkpoint is not None:
            raise AppError("unexpected_data_checkpoint_argument",400)
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
            if action in ("start","restart"):
                _confirm_ready(project,manifest,entry["owner"])
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
            _confirm_ready(project,target,entry["owner"])
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
