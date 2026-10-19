"""Generalized, catalog-derived, stage-only single-service install lifecycle.

Installability != application functional parity. The Compose definition is
NEVER executed. A new ephemeral container is made with fixed restrictions,
an optional original image cached locally, no network, no public ports,
and only remapped stage-owned volume directories. Never operates on a
CasaOS production container or the user's external HDD.
"""
from __future__ import annotations
from stage_container_health import status as stage_health_status
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import time
from pathlib import Path
from urllib.parse import unquote
import yaml

from stage_apps import STAGE, AppError, guarded, registry as manager_registry
from casaos_appstore import STORE_ROOT, indexed_definition, SAFE_LOADER

ROOT=STAGE/"store-general"
DATABASE=ROOT/"installations.json"
MAX_INSTALLS=3
MAX_MOUNTS=5
MAX_BYTES=262144
ID_PATTERN=re.compile(r"osd-store-[a-f0-9]{12}\Z")
CID_PATTERN=re.compile(r"[a-f0-9]{64}\Z")
IMAGE_PATTERN=re.compile(r"[a-zA-Z0-9][a-zA-Z0-9./_-]{1,180}:[a-zA-Z0-9_.-]{1,90}\Z")
CATALOG_IMAGE_PATTERN=re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,180}(?::[A-Za-z0-9_.-]{1,90})?\Z")
IMAGE_ID_PATTERN=re.compile(r"sha256:[a-f0-9]{64}\Z")
SAFE_TARGET=re.compile(r"/[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)*\Z")
BANNED_TARGETS=("/proc","/sys","/dev","/run","/var/run","/etc","/root","/home","/mnt","/media")

def _command(*args, timeout=55):
    try:
        proc=subprocess.run(("docker",*args),capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired):
        raise AppError("stage_store_engine_unavailable",503)
    if proc.returncode or len(proc.stdout)>120000:
        raise AppError("stage_store_engine_action_failed",503)
    return proc.stdout.strip()

def _root():
    if ROOT.is_symlink():
        raise AppError("unsafe_stage_store_root",503)
    if not ROOT.exists(): ROOT.mkdir(mode=0o700)
    if not ROOT.is_dir() or ROOT.stat().st_mode & 0o077:
        raise AppError("unsafe_stage_store_root",503)
    return ROOT

def _safe_project_storage(project, mounts):
    if not ID_PATTERN.fullmatch(project):
        raise AppError("invalid_store_project",400)
    root=_root()/project
    base=root/"data"
    # Prevent an operator-created symlink/mount from making Docker access
    # the external HDD when an installed container restarts.
    for path in (root,base,*(base/str(n) for n in range(len(mounts)))):
        if (not path.is_dir() or path.is_symlink()
            or path.stat().st_dev != STAGE.stat().st_dev):
            raise AppError("unsafe_stage_volume_boundary",403)
    return base

def _state():
    _root()
    if DATABASE.is_symlink():
        raise AppError("stage_store_registry_symlink",503)
    if not DATABASE.is_file():return {}
    try:
        entries=json.loads(DATABASE.read_text())
        if not isinstance(entries,dict) or len(entries)>MAX_INSTALLS:
            raise ValueError("bad registry")
        for project, item in entries.items():
            if (not ID_PATTERN.fullmatch(project) or not isinstance(item,dict)
                or set(item)!={"container","owner","app_id","image","mounts"}
                or not CID_PATTERN.fullmatch(item["container"])
                or not re.fullmatch(r"[a-f0-9]{32}",item["owner"])
                or not isinstance(item["app_id"],str)
                or not IMAGE_PATTERN.fullmatch(item["image"])
                or not isinstance(item["mounts"],list)
                or len(item["mounts"])>MAX_MOUNTS
                or any(not isinstance(m,str) or not SAFE_TARGET.fullmatch(m)
                       for m in item["mounts"])):
                raise ValueError("invalid staged store record")
        return entries
    except (OSError,ValueError,TypeError):
        raise AppError("stage_store_registry_invalid",503)

def _save(entries):
    temp=_root()/(".store-install-"+secrets.token_hex(8))
    try:
        with temp.open("x") as fh:
            json.dump(entries,fh,sort_keys=True)
            fh.flush();os.fsync(fh.fileno())
        temp.chmod(0o600)
        os.replace(temp,DATABASE)
        fd=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:temp.unlink(missing_ok=True)

def _find_catalog_definition(app_id):
    if not isinstance(app_id,str) or len(app_id)>115 or not re.fullmatch(r"[A-Za-z0-9_.:-]+",app_id):
        raise AppError("invalid_store_app_id",400)
    try:
        known,path=indexed_definition(app_id)
    except (ValueError,OSError) as err:
        if str(err)=="unknown store app":
            raise AppError("unknown_store_app_id",404) from err
        raise AppError("store_metadata_changed_or_unavailable",409) from err
    if path.lstat().st_size>MAX_BYTES:
        raise AppError("store_definition_exceeds_limits",409)
    try:
        with path.open("r",encoding="utf-8") as handle:
            doc=yaml.load(handle,Loader=SAFE_LOADER)
    except (OSError,UnicodeError,yaml.YAMLError):
        raise AppError("invalid_casaos_compose_definition",409)
    return known,doc

def _mount_targets(service):
    volumes=service.get("volumes") or []
    if not isinstance(volumes,list) or len(volumes)>MAX_MOUNTS:
        raise AppError("unsafe_volume_count",409)
    output=[]
    for item in volumes:
        if isinstance(item,str):
            fragments=item.split(":")
            if len(fragments)<2 or len(fragments)>3:
                raise AppError("unsupported_volume_mapping",409)
            target=fragments[1]
        elif isinstance(item,dict):
            target=item.get("target")
            if item.get("type") not in ("bind","volume"):
                raise AppError("unsupported_volume_type",409)
        else:raise AppError("invalid_compose_volume",409)
        if (not isinstance(target,str) or not SAFE_TARGET.fullmatch(target)
            or any(target==x or target.startswith(x+"/") for x in BANNED_TARGETS)
            or target in output):
            raise AppError("unsafe_container_volume_target",409)
        output.append(target)
    return output

def preflight(app_id):
    known, doc=_find_catalog_definition(app_id)
    service_map=doc.get("services") if isinstance(doc,dict) else None
    if not isinstance(service_map,dict) or len(service_map)!=1:
        return {"id":app_id,"eligible":False,"reason":"multiservice_requires_separate_isolated_runtime"}
    service=next(iter(service_map.values()))
    if not isinstance(service,dict):
        return {"id":app_id,"eligible":False,"reason":"invalid_compose_service"}
    # The original privileged/network/deploy/port settings are deliberately
    # NEVER copied. Apps are assessed for running with reduced functionality
    # in an isolated container. Only fields requiring a different execution
    # model are rejected.
    forbidden=("build","devices","cap_add","pid","ipc","userns_mode",
               "security_opt","extra_hosts","volumes_from","links","extends",
               "entrypoint","command")
    if any(key in service for key in forbidden):
        return {"id":app_id,"eligible":False,"reason":"advanced_runtime_options_not_sandbox_safe"}
    image=service.get("image")
    if not isinstance(image,str) or not CATALOG_IMAGE_PATTERN.fullmatch(image):
        return {"id":app_id,"eligible":False,"reason":"unsupported_image_reference"}
    try:
        mounts=_mount_targets(service)
    except AppError:
        return {"id":app_id,"eligible":False,"reason":"unsafe_app_volume_declaration"}
    try:
        # Resolve a mutable tag to the locally present IMMUTABLE image ID.
        # No network image fetch occurs during preflight or installation.
        cached_id=_command("image","inspect","--format","{{.Id}}",image,timeout=12)
        if not IMAGE_ID_PATTERN.fullmatch(cached_id):
            raise AppError("unrecognized_cached_image_identity",409)
        cached=True
    except AppError:
        cached=False
        cached_id=None
    return {
        "id":app_id,"title":known["title"],"image":image,
        "eligible":True,"image_cached":cached,"image_id":cached_id,
        "immutable_image_id_verified":bool(cached_id),
        "mount_count":len(mounts),
        "host_ports_exposed":False,"network_enabled":False,
        "environment_from_source_applied":False,
        "source_host_features_stripped":sorted(x for x in
            ("ports","privileged","network_mode","deploy","environment",
             "env_file","restart") if x in service),
        "staging_only":True,"production_mutation_allowed":False,
        "reason": "image_cached_install_ready" if cached else "exact_image_not_cached",
    }

def _container(project, record):
    ident=record["container"]
    if not CID_PATTERN.fullmatch(ident):raise AppError("invalid_store_container_id",403)
    try:obj=json.loads(_command("inspect","--type","container",ident,timeout=20))[0]
    except (ValueError,TypeError,KeyError,IndexError):
        raise AppError("stage_store_container_missing",503)
    cfg=obj.get("Config") or {}
    host=obj.get("HostConfig") or {}
    labels=cfg.get("Labels") or {}
    mounts=obj.get("Mounts") or []
    expected={
        "osd.store.general":"stage-isolated",
        "osd.store.owner":record["owner"],
        "osd.store.project":project,
        "osd.store.app_id":record["app_id"],
    }
    root=_root()/project
    _safe_project_storage(project,record["mounts"])
    if (not root.is_dir() or root.is_symlink()
        or obj.get("Id")!=ident or cfg.get("Image")!=record["image"]
        or cfg.get("User")!="1000:1000"
        or any(labels.get(k)!=v for k,v in expected.items())
        or host.get("NetworkMode")!="none"
        or host.get("Privileged") is not False
        or host.get("PortBindings") or host.get("Binds")
        or any(m.get("Type")!="bind" or m.get("RW") is not True
               or m.get("Source")!=str(root/"data"/str(i))
               or m.get("Destination")!=target
               for i,(m,target) in enumerate(zip(mounts,record["mounts"])))
        or len(mounts)!=len(record["mounts"])):
        raise AppError("store_container_owner_or_isolation_mismatch",403)
    status=obj.get("State") or {}
    return {"project":project,"id":ident[:12],"app_id":record["app_id"],
            "image":record["image"],"running":bool(status.get("Running")),
            "health_status":stage_health_status(status),
            "staging_only":True,"production_mutation_allowed":False}

def listing():
    with guarded():
        return {"apps":[_container(p,e) for p,e in sorted(_state().items())],
                "scope":"catalog_derived_isolated_singlestage",
                "production_mutation_allowed":False}

def action(op, app_id=None, project=None):
    if op not in {"install","prepare","start","stop","restart","uninstall"}:
        raise AppError("invalid_store_general_operation",400)
    with guarded():
        records=_state()
        if op=="prepare":
            if project is not None or not isinstance(app_id,str):
                raise AppError("invalid_stage_image_prepare",400)
            plan=preflight(app_id)
            if not plan.get("eligible"):
                raise AppError(plan.get("reason","store_not_eligible"),409)
            if plan["image_cached"]:
                return {"operation":"already_cached","app_id":app_id,
                        "production_mutation_allowed":False}
            # The image is downloaded into Docker's cache only after a
            # privileged staging operator explicitly requests preparation.
            # Never execute downloaded code as part of image preparation.
            space=shutil.disk_usage("/var/lib/docker")
            if space.free < 8 * 1024**3:
                raise AppError("insufficient_safe_docker_disk_headroom",409)
            _command("pull",plan["image"],timeout=240)
            meta=json.loads(_command("image","inspect",plan["image"],timeout=15))
            if (not isinstance(meta,list) or len(meta)!=1
                or int(meta[0].get("Size",0))>1_000_000_000):
                raise AppError("cached_store_image_exceeds_stage_size_limit",409)
            return {"operation":"prepared","app_id":app_id,
                    "image":plan["image"],
                    "production_mutation_allowed":False}
        if op=="install":
            if project is not None or len(records)>=MAX_INSTALLS:
                raise AppError("stage_store_install_capacity",409)
            plan=preflight(app_id)
            if not plan.get("eligible") or not plan.get("image_cached"):
                raise AppError(plan.get("reason","stage_app_not_eligible"),409)
            # All container launches must use the exact cached image ID;
            # never pass a mutable latest/unversioned tag to Docker run.
            image_id=plan["image_id"]
            if not isinstance(image_id,str) or not IMAGE_ID_PATTERN.fullmatch(image_id):
                raise AppError("staging_image_identity_not_verified",409)
            _,doc=_find_catalog_definition(app_id)
            service=next(iter(doc["services"].values()))
            targets=_mount_targets(service)
            project="osd-store-"+secrets.token_hex(6)
            root=_root()/project
            data=root/"data"
            data.mkdir(mode=0o700,parents=True)
            owner=manager_registry()["owner"]
            for idx in range(len(targets)):
                (data/str(idx)).mkdir(mode=0o700)
            _safe_project_storage(project,targets)
            args=["run","--detach","--pull","never","--name",project,
                  "--network","none","--cap-drop","ALL",
                  "--security-opt","no-new-privileges","--memory","256m",
                  "--pids-limit","64","--user","1000:1000",
                  "--tmpfs","/tmp:rw,nosuid,noexec,size=16m"]
            for idx,target in enumerate(targets):
                args.extend(["--mount",f"type=bind,src={data/str(idx)},dst={target}"])
            for label,value in (
                ("osd.store.general","stage-isolated"),
                ("osd.store.owner",owner),
                ("osd.store.project",project),
                ("osd.store.app_id",app_id)):
                args.extend(["--label",f"{label}={value}"])
            # Even when the source has privileged flags, env or ports,
            # none of those dangerous fields enter the Docker command.
            ident=_command(*args,image_id,timeout=65)
            if not CID_PATTERN.fullmatch(ident):
                raise AppError("unrecognized_new_stage_container",503)
            record={"container":ident,"owner":owner,"app_id":app_id,
                    "image":image_id,"mounts":targets}
            try:
                _container(project,record)
                time.sleep(2)
                state=_container(project,record)
                if not state["running"]:
                    raise AppError("stage_app_startup_failed",503)
            except AppError:
                # ONLY the exact newly created container ID is removed.
                _command("rm","--force",ident)
                raise
            records[project]=record
            _save(records)
            return {"operation":"installed","app":state}
        if app_id is not None or project not in records:
            raise AppError("unknown_staged_store_project",404)
        record=records[project]
        prior=_container(project,record)
        if op=="start":
            if prior["running"]:raise AppError("already_running",409)
            _command("start",record["container"])
        elif op=="stop":
            if not prior["running"]:raise AppError("already_stopped",409)
            _command("stop","--time","2",record["container"])
        elif op=="restart":
            if not prior["running"]:raise AppError("not_running",409)
            _command("restart","--time","2",record["container"])
        else:
            _command("rm","--force",record["container"])
            records.pop(project)
            _save(records)
            return {"operation":"uninstalled","project":project,
                    "stage_data_retained":True,"production_mutation_allowed":False}
        return {"operation":op,"app":_container(project,record)}
