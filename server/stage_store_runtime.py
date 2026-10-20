"""Isolated compiled CasaOS App Store multi-service runtime.

Only deploy compiler-created cached immutable images, no host ports/network,
no original user bind paths. Stage configuration image revisions can be
reverted. Rollback DOES NOT restore mutable application databases.
"""
from __future__ import annotations
import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import subprocess
import time
from pathlib import Path
from stage_apps import AppError, guarded, registry as user_registry
from stage_multiservice_health import assess as assess_multiservice_health
from stage_store_compiler import compile_stage, prepare_images, STAGE
from stage_store_general import MAX_MOUNTS
from stage_qui_pilot import APP as QUI_APP, create as qui_secret_create, allow_configuration as qui_allow, allow_configuration_readonly as qui_readonly_allow
from stage_postgres_integrity import is_qui_pg
from stage_store_data import (
    listing as data_listing, checkpoint as data_checkpoint,
    restore as data_restore, recover as data_recover,
    _validate_snapshot as _data_validate,
    _save as _data_save,
    _apply as _data_apply,
    delete_checkpoint as data_delete)

ROOT=Path(STAGE)
STATE=ROOT/"registry.json"
PROJECT=re.compile(r"osd-compiled-[0-9a-f]{12}\Z")
CID=re.compile(r"[0-9a-f]{64}\Z")
OWNER=re.compile(r"[0-9a-f]{32}\Z")
IMMUTABLE=re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_PROJECTS=6
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


def _dependency_map(manifest):
    services=manifest.get("services")
    if not isinstance(services,dict) or not 1<=len(services)<=6:
        raise AppError("invalid_compiled_services",403)
    edges={}
    for name,cfg in services.items():
        raw=cfg.get("depends_on",[])
        if isinstance(raw,list):
            deps={dep:"service_started" for dep in raw}
            if len(deps)!=len(raw):
                raise AppError("duplicate_compiled_dependency",403)
        elif isinstance(raw,dict):
            deps={}
            for dep,condition in raw.items():
                if (not isinstance(condition,dict) or set(condition)!={"condition"}
                        or condition["condition"] not in ("service_started","service_healthy")):
                    raise AppError("unsafe_compiled_dependency_condition",403)
                deps[dep]=condition["condition"]
        else:
            raise AppError("invalid_compiled_dependency",403)
        if any(not isinstance(dep,str) or dep not in services or dep==name for dep in deps):
            raise AppError("unsafe_compiled_dependency_reference",403)
        edges[name]=deps
    return edges

def _startup_order(manifest):
    edges=_dependency_map(manifest)
    done=set()
    active=set()
    order=[]
    def visit(name):
        if name in active:
            raise AppError("cyclic_compiled_dependencies",403)
        if name in done:return
        active.add(name)
        for dep in sorted(edges[name]):visit(dep)
        active.remove(name)
        done.add(name)
        order.append(name)
    for name in sorted(edges):visit(name)
    return order

def _ordered_stops(services):
    # Uses dependencies already proven by _owned against the stage manifest.
    edges={n:set(x.get("depends_on",[])) for n,x in services.items()}
    order=[]
    visiting=set()
    def visit(name):
        if name in visiting:raise AppError("cyclic_compiled_dependencies",403)
        if name in order:return
        visiting.add(name)
        for dep in sorted(edges[name]):
            if dep not in services:raise AppError("unsafe_compiled_dependency_reference",403)
            visit(dep)
        visiting.remove(name)
        order.append(name)
    for name in sorted(services):visit(name)
    return list(reversed(order))

def _wait_for_dependency(project,manifest,owner,service,grace_seconds=22):
    dependencies=_dependency_map(manifest)[service]
    if not dependencies:return
    deadline=time.monotonic()+grace_seconds
    while True:
        current=_owned(project,manifest,owner)
        states={name:(current[name]["running"] and (
            condition=="service_started" or current[name].get("health")=="healthy"))
                for name,condition in dependencies.items()}
        if all(states.values()):return
        # A service_healthy dependency without a Docker healthcheck
        # can never be fulfilled; reject instead of starting the dependent.
        if any(condition=="service_healthy" and
               current[name].get("health") is None
               for name,condition in dependencies.items()):
            raise AppError("compiled_dependency_healthcheck_missing",503)
        if any(current[name].get("health")=="unhealthy"
               for name in dependencies):
            raise AppError("compiled_dependency_unhealthy",503)
        if time.monotonic()>=deadline:
            raise AppError("compiled_dependency_not_ready",503)
        time.sleep(1)

def _tcp_ready(port):
    if port is None:return True
    try:
        with socket.create_connection(("127.0.0.1",port),timeout=0.5):
            return True
    except OSError:
        return False

def _stage_private_endpoint(project,manifest,owner,services=None):
    """Resolve only the Docker-verified internal-stage app service/IP.

    Prevent arbitrary URLs or project IDs from influencing the target.
    """
    if manifest.get("networks")!={"isolated":{"internal":True}}:
        raise AppError("not_an_internal_stage_network",403)
    network=project+"_isolated"
    wanted=[]
    for name,spec in manifest["services"].items():
        for port in spec.get("ports",[]):
            match=PORT.fullmatch(port)
            if match:wanted.append((name,int(match.group(2))))
    if len(wanted)!=1:
        raise AppError("internal_stage_web_port_unavailable",409)
    name,port=wanted[0]
    items=services if services is not None else _owned(project,manifest,owner)
    if name not in items:
        raise AppError("stage_internal_target_missing",503)
    obj=json.loads(docker("inspect","--type","container",items[name]["id"]))[0]
    nets=(obj.get("NetworkSettings") or {}).get("Networks") or {}
    if set(nets)!={network}:
        raise AppError("stage_internal_network_identity_changed",403)
    address=nets[network].get("IPAddress")
    try: ip=ipaddress.ip_address(address)
    except ValueError:
        raise AppError("stage_internal_ip_invalid",503)
    if ip.version!=4 or not ip.is_private or ip.is_loopback or ip.is_link_local:
        raise AppError("stage_internal_ip_not_private",403)
    return str(ip),port

def _private_ready(project,manifest,owner,services):
    try:
        ip,port=_stage_private_endpoint(project,manifest,owner,services)
        with socket.create_connection((ip,port),timeout=0.5):
            return True
    except (AppError,OSError):
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
        # Dependency-aware readiness does not treat an unhealthy database
        # as a healthy deployment just because the web TCP port opened.
        required_healthy={name for cfg in _dependency_map(manifest).values()
                          for name,condition in cfg.items()
                          if condition=="service_healthy"}
        health_good=all(s.get("health") not in ("starting","unhealthy")
                        for s in services.values())
        healthy_ready=all(services[name].get("health")=="healthy"
                          for name in required_healthy)
        if manifest.get("networks")=={"isolated":{"internal":True}} and port is not None:
            web_ready=_private_ready(project,manifest,owner,services)
        else:
            web_ready=_tcp_ready(port)
        reachable=running and health_good and healthy_ready and web_ready
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

def _validate(project,manifest,owner,*,read_only=False):
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
        pilot_env=bool(cfg.get("environment") or cfg.get("healthcheck"))
        if (not network_ok or cfg.get("user")!="1000:1000"
            or cfg.get("pull_policy")!="never" or cfg.get("cap_drop")!=["ALL"]
            or cfg.get("security_opt")!=["no-new-privileges:true"]
            or cfg.get("restart")!="no" or cfg.get("labels")!=expected
            or cfg.get("privileged")
            or (pilot_env and not (
                qui_readonly_allow(project,services) if read_only
                else qui_allow(project,services)))
            or cfg.get("env_file")
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
        if not isinstance(mounts,list) or len(mounts)>MAX_MOUNTS:
            raise AppError("unsafe_compiled_volume_count",403)
        for mount in mounts:
            if not isinstance(mount,dict) or set(mount)!={"type","source","target","bind"}:
                raise AppError("unsafe_compiled_stage_mount",403)
            src=Path(mount["source"])
            if (mount["type"]!="bind" or mount["bind"]!={"create_host_path":False}
                or src not in [base/name/("volume-"+str(i)) for i in range(MAX_MOUNTS)]
                or not src.is_dir() or src.is_symlink()
                or src.stat().st_dev!=ROOT.stat().st_dev):
                raise AppError("unsafe_compiled_stage_volume",403)
            used.append(str(src))
    # Validate the full graph, including dependency condition and cycles.
    _startup_order(manifest)
    if len(used)!=len(set(used)):
        raise AppError("duplicate_compiled_stage_volume",403)
    if len(public)>1:
        raise AppError("too_many_compiled_public_ports",403)

def _compose_path(project):
    return _file(_folder(project)/"compose.json")

def _owned(project,manifest,owner,*,read_only=False):
    _validate(project,manifest,owner,read_only=read_only)
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
        # Prove the running containers actually use the exact stage-only
        # credentials/healthcheck from the root-protected pilot record.
        if spec.get("environment"):
            observed=set(cfg.get("Env") or [])
            if any(k+"="+v not in observed for k,v in spec["environment"].items()):
                raise AppError("compiled_container_environment_drift",403)
        if spec.get("healthcheck"):
            observed_health=(cfg.get("Healthcheck") or {}).get("Test")
            if observed_health!=spec["healthcheck"]["test"]:
                raise AppError("compiled_container_healthcheck_drift",403)
        _network_check(project,manifest,spec,host,obj)
        state=obj.get("State") or {}
        health=(state.get("Health") or {}).get("Status")
        if health not in (None,"starting","healthy","unhealthy"):
            raise AppError("compiled_container_health_invalid",503)
        seen[name]={"name":name,"id":ident,"running":bool(state.get("Running")),
                    "status":state.get("Status","unknown"),
                    "exit_code":state.get("ExitCode") if state.get("Status")=="exited" else None,
                    "oom_killed":state.get("OOMKilled") is True,
                    "health":health,
                    "depends_on":sorted(_dependency_map(manifest)[name])}
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

def _current(project,entry,*,read_only=False):
    folder=_folder(project)
    if folder.is_symlink() or not folder.is_dir():
        raise AppError("compiled_stage_project_dir_invalid",403)
    manifest=_read(_compose_path(project),None)
    if not isinstance(manifest,dict):
        raise AppError("compiled_stage_manifest_missing",503)
    services=_owned(project,manifest,entry["owner"],read_only=read_only)
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

def _summary(project,entry,*,read_only=False):
    manifest,services=_current(project,entry,read_only=read_only)
    service_rows=[
        {"name":s["name"],"running":s["running"],
         "status":s["status"],"exit_code":s["exit_code"],
         "oom_killed":s["oom_killed"],"health":s["health"],
         "depends_on":s["depends_on"]}
        for s in sorted(services.values(),key=lambda x:x["name"])
    ]
    assessment=assess_multiservice_health(service_rows)
    health_by_name={s["name"]:s for s in assessment["services"]}
    for row in service_rows:
        row["readiness"]=health_by_name[row["name"]]["readiness"]
    return {"project":project,"app_id":entry["app_id"],
            "revision":entry["revision"],
            "health_inspection_only": bool(read_only and entry["app_id"]==QUI_APP),
            "credential_provenance": (
                "root_protected_unverified" if read_only and entry["app_id"]==QUI_APP
                else "not_applicable"),

            "services":service_rows,
            "health_summary":{key:value for key,value in assessment.items()
                              if key!="services"},
            "startup_order":_startup_order(manifest),
            "all_running":all(x["running"] for x in services.values()),
            "outbound_network_pilot":_network_contract(manifest)[0]=="egress" if "networks" in manifest else False,
            "image_configuration_rollback":True,
            "application_data_rollback":(
                _read(_version_link(project),None) is not None),
            "revision_data_checkpoint":(
                (_read(_version_link(project),None) or {}).get("checkpoint")),
            "manual_stage_volume_backup_restore":True,
            "data_checkpoints":data_listing(project,manifest),
            "data_recovery_pending":(_folder(project)/"data-restore-pending.json").exists(),
            "online_data_recovery_pending":_online_file(project).exists(),
            "web_url":("http://127.0.0.1:"+str(_published_port(manifest))
                       if _published_port(manifest) is not None and
                          manifest.get("networks")!={"isolated":{"internal":True}}
                       else None),
            "stage_browser_app":(entry["app_id"] in (QUI_APP,"default:MySpeed")
                                 and _published_port(manifest) is not None),
            "production_mutation_allowed":False}

def _online_file(project):
    return _file(_folder(project)/"online-data-pending.json")

def _stop_for_online(services):
    # Dependents must shut down before their data/database dependencies.
    for name in _ordered_stops(services):
        s=services[name]
        if s["running"]:
            docker("stop","--time","3",s["id"])

def _resume_online(project,manifest,owner,running):
    """Resume only services that were running before the online operation."""
    current=_owned(project,manifest,owner)
    if set(running)!=set(current):
        raise AppError("stage_online_service_layout_changed",503)
    # Restore the service graph in dependency order; do not start the web
    # service before its DB has started or passed required healthchecks.
    for name in _startup_order(manifest):
        s=current[name]
        if name in running and not s["running"]:
            _wait_for_dependency(project,manifest,owner,name)
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
                    "sqlite_files_verified":saved["sqlite_files_verified"],
                    "postgresql_cold_verified":saved.get("postgresql_cold_verified",False)}
        else:
            # Preserve exact pre-restore bytes BEFORE mutating anything.
            # The journal pins this undo checkpoint durably.
            record["undo"]=_data_save(project,manifest)
            _atomic(path,record)
            checked=_data_apply(project,manifest,checkpoint)
            result={"operation":"restored_online","checkpoint":checkpoint,
                    "undo":record["undo"],"sqlite_files_verified":checked,
                    "postgresql_cold_verified":is_qui_pg(manifest)}
        _resume_online(project,manifest,entry["owner"],set(running))
        path.unlink()
        result.update({"production_mutation_allowed":False,"app":_summary(project,entry)})
        return result
    except Exception as err:
        # Leave a durable journal. No blind automatic retry after a crash.
        raise AppError("stage_online_data_requires_recovery",503) from err

def _manifest_sha(manifest):
    return hashlib.sha256(json.dumps(manifest,sort_keys=True,
                                     separators=(",",":")).encode("utf-8")).hexdigest()

def _version_link(project):
    return _file(_folder(project)/"previous-data.json")

def _check_version_link(project,target,doc):
    if (not isinstance(doc,dict) or set(doc)!={"manifest_sha256","checkpoint"}
            or doc.get("manifest_sha256")!=_manifest_sha(target)):
        raise AppError("stage_previous_data_link_missing_or_mismatched",409)
    # Enforce manifest and database integrity before stopping ANY container.
    _data_validate(project,target,doc["checkpoint"])
    return doc["checkpoint"]

def _recover_versioned(project,entry,state,values,journal):
    """Restore pre-operation config and exact pre-operation staging bytes.

    Any unproven/mixed container identity halts without touching it.
    """
    old=state.get("old")
    target=state.get("target")
    backup=state.get("backup")
    running=state.get("running")
    owner=entry.get("owner")
    if (not isinstance(old,dict) or not isinstance(target,dict)
            or not isinstance(owner,str) or not OWNER.fullmatch(owner)
            or type(state.get("revision")) is not int
            or not isinstance(running,list)
            or len(running)!=len(set(running))
            or any(not isinstance(n,str) or n not in old.get("services",{}) for n in running)):
        raise AppError("invalid_stage_version_recovery_journal",503)
    _validate(project,old,owner)
    _validate(project,target,owner)
    if backup is not None:
        _data_validate(project,old,backup)
    # Enforce provenance for ALL containers before stop, using either
    # the exact old or exact new immutable manifest, never project label alone.
    verified=None
    for spec in (target,old):
        try:
            verified=_verify_partial(project,spec,owner)
            break
        except AppError:
            continue
    if verified is None:
        raise AppError("stage_version_recovery_unverified_containers",403)
    for ident in verified:
        docker("stop","--time","3",ident)
    if backup is not None:
        _data_apply(project,old,backup)
    _atomic(_compose_path(project),old)
    _up(project)
    _resume_online(project,old,owner,set(running))
    previous=_file(_folder(project)/"previous.json")
    prior=state.get("prior")
    prior_data=state.get("prior_data")
    if prior is None:
        previous.unlink(missing_ok=True)
    else:
        _atomic(previous,prior)
    if prior_data is None:
        _version_link(project).unlink(missing_ok=True)
    else:
        _atomic(_version_link(project),prior_data)
    entry["revision"]=state["revision"]
    _atomic(STATE,values)
    journal.unlink()
    return {"operation":"recovered_version_with_data",
            "restored_checkpoint":backup,
            "application_data_rollback":backup is not None,
            "production_mutation_allowed":False}

def _versioned_change(project,entry,values,manifest,services,action,target,journal,previous):
    """Quiesce, checkpoint, replace config, and link exact pre-update data."""
    owner=entry["owner"]
    running=sorted(name for name,s in services.items() if s["running"])
    previous_data=_version_link(project)
    prior=_read(previous,None)
    prior_data=_read(previous_data,None)
    rollback_cp=None
    if action=="rollback":
        rollback_cp=_check_version_link(project,target,prior_data)
    # Unmodified startup/read-only inspection before durable mutation.
    record={"version":2,"operation":action,"old":manifest,"target":target,
            "revision":entry["revision"],"running":running,
            "backup":None,"prior":prior,"prior_data":prior_data}
    _atomic(journal,record)
    try:
        _stop_for_online(services)
        if any(item["running"] for item in _owned(project,manifest,owner).values()):
            raise AppError("stage_version_stop_incomplete",503)
        record["backup"]=_data_save(project,manifest)
        _atomic(journal,record)
        if rollback_cp is not None:
            # Restore linked DB snapshot while old containers are stopped.
            _data_apply(project,target,rollback_cp)
        _atomic(_compose_path(project),target)
        _up(project)
        _resume_online(project,target,owner,set(running))
        # New rollback link always references the configuration and data
        # that existed immediately before this particular version change.
        _atomic(previous,manifest)
        _atomic(previous_data,{"checkpoint":record["backup"],
                               "manifest_sha256":_manifest_sha(manifest)})
        entry["revision"]+=1
        _atomic(STATE,values)
        journal.unlink()
        return {"operation":action,"data_checkpoint":record["backup"],
                "data_restored":rollback_cp is not None,
                "application_data_rollback":True,
                "production_mutation_allowed":False,
                "app":_summary(project,entry)}
    except Exception as err:
        try:
            outcome=_recover_versioned(project,entry,record,values,journal)
        except Exception as failed:
            # Retain the durable journal for explicit operator recovery.
            raise AppError("stage_version_change_requires_recovery",503) from failed
        raise AppError("stage_version_change_failed_original_and_data_restored",503) from err

def listing():
    try:
        with guarded():
            root=_root()
            values=_projects()
            pending=[]
            unregistered=[]
            for child in root.iterdir():
                if PROJECT.fullmatch(child.name) and not child.is_symlink():
                    if child.name not in values:
                        # Legacy root-only projects are NOT managed by this
                        # registry. Do not traverse their protected data.
                        unregistered.append(child.name)
                        continue
                    j=child/"pending.json"
                    if j.is_file() or j.is_symlink():
                        pending.append(child.name)
            apps=[]
            restricted=[]
            for project,entry in sorted(values.items()):
                if project in pending:
                    continue
                try:
                    apps.append(_summary(project,entry,
                                         read_only=(entry["app_id"]==QUI_APP)))
                except AppError as err:
                    if (entry["app_id"]==QUI_APP and
                            err.message=="qui_stage_secret_access_denied"):
                        restricted.append({"project":project,
                                           "reason":"protected_stage_credentials"})
                    else:
                        # Provenance violations and other faults must not
                        # silently downgrade to a partial-success listing.
                        raise
            return {"apps":apps,
                    "capacity":{"limit":MAX_PROJECTS,
                                "installed":len(values),
                                "available":MAX_PROJECTS-len(values)},
                    "unavailable_projects":restricted,
                    "complete":not restricted and not pending,
                    "pending_recovery":sorted(pending),
                    "unregistered_stage_directories":sorted(unregistered),
                    "scope":"isolated_compiled_appstore_runtime",
                    "application_data_rollback":any(a["application_data_rollback"] for a in apps),
                    "migration_allowed":False,"production_mutation_allowed":False}
    except PermissionError as err:
        # Never bypass root-protected staging recovery/credential files.
        raise AppError("compiled_stage_metadata_permission_denied",503) from err

def operation(action,app_id=None,project=None,checkpoint=None):
    if action not in ("prepare","install","finish-install","start","stop","restart","uninstall","update","rollback","recover",
                      "checkpoint","restore-data","recover-data",
                      "backup-online","restore-online","recover-online","delete-checkpoint"):
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
            folder=_folder(project)
            folder.mkdir(mode=0o700)
            if app_id==QUI_APP:
                qui_secret_create(project)
            raw=compile_stage(project,app_id,host_port=_pick_port(project))
            owner=user_registry()["owner"]
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
                _confirm_ready(project,manifest,owner,
                               grace_seconds=25 if app_id==QUI_APP else 11)
                values[project]={"app_id":app_id,"owner":owner,"revision":1}
                _atomic(STATE,values)
                journal.unlink()
            except Exception:
                raise
            return {"operation":"installed","app":_summary(project,values[project])}
        if action=="finish-install":
            if (checkpoint is not None or app_id is not None
                    or not isinstance(project,str) or not PROJECT.fullmatch(project)
                    or project in values):
                raise AppError("invalid_stage_install_finalization",400)
            folder=_folder(project)
            journal=_file(folder/"pending.json")
            state=_read(journal,None)
            if not isinstance(state,dict) or state.get("operation")!="install":
                raise AppError("no_pending_stage_install",404)
            owner=state.get("owner")
            if not isinstance(owner,str) or not OWNER.fullmatch(owner):
                raise AppError("invalid_stage_install_owner",403)
            manifest=_read(_compose_path(project),None)
            if not isinstance(manifest,dict):
                raise AppError("missing_stage_install_manifest",503)
            _validate(project,manifest,owner)
            _confirm_ready(project,manifest,owner,grace_seconds=3)
            if len(values)>=MAX_PROJECTS:
                raise AppError("compiled_stage_capacity",409)
            app_id=state.get("app_id")
            if app_id!=QUI_APP:
                raise AppError("install_finalization_not_approved_for_app",403)
            values[project]={"app_id":app_id,"owner":owner,"revision":1}
            _atomic(STATE,values)
            journal.unlink()
            return {"operation":"installed_after_readiness","app":_summary(project,values[project])}
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
            elif state.get("version")==2 and state["operation"] in ("update","rollback"):
                entry=values.get(project)
                if not isinstance(entry,dict):
                    raise AppError("compiled_rollback_evidence_unavailable",503)
                result=_recover_versioned(project,entry,state,values,journal)
                return {"project":project,"scope":"isolated_compiled_stage_only",**result}
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
        if action=="delete-checkpoint":
            return data_delete(project,manifest,checkpoint)
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
            original={name for name,item in services.items() if item["running"]}
            if action in ("stop","restart"):
                for name in _ordered_stops(services):
                    if services[name]["running"]:
                        docker("stop","--time","2",services[name]["id"])
            if action in ("start","restart"):
                current=_owned(project,manifest,entry["owner"])
                for name in _startup_order(manifest):
                    if action=="start" or name in original:
                        if not current[name]["running"]:
                            _wait_for_dependency(project,manifest,entry["owner"],name)
                            docker("start",current[name]["id"])
                if action=="start" or len(original)==len(services):
                    _confirm_ready(project,manifest,entry["owner"])
            return {"operation":action,"app":_summary(project,entry)}
        # Version changes are now accompanied by cold stage-volume snapshots
        # and an exact config-linked restore checkpoint.
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
        return _versioned_change(project,entry,values,manifest,services,
                                 action,target,journal,previous)
