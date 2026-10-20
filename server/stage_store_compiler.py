"""Safe, read-only compiler for local CasaOS App Store multi-service metadata.

Does not execute any original Compose file or touch production volumes.
Builds a stage-only plan with immutable image IDs from Docker's local cache.
"""
from __future__ import annotations
import re
import shutil
import subprocess
from stage_store_general import _find_catalog_definition, _mount_targets, AppError, _read_only_targets
from stage_host_socket import (
    eligible as host_socket_eligible,
    adapted_service as host_socket_adapted,
    socket_mount as host_socket_mount,
    approved_service as host_socket_service,
    LABEL as HOST_SOCKET_LABEL, LABEL_VALUE as HOST_SOCKET_LABEL_VALUE,
)
from stage_qui_pilot import APP as QUI_APP, supported as qui_supported, environments as qui_environments, HEALTH as QUI_HEALTH

MAX_SERVICES=12
MAX_TOTAL_MOUNTS=64
NAME=re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,35}\Z")
IMAGE=re.compile(r"[A-Za-z0-9][A-Za-z0-9./_:-]{1,240}(?:@sha256:[0-9a-f]{64})?\Z")
DIGEST=re.compile(r"sha256:[0-9a-f]{64}\Z")
STAGE="/opt/openserverdesk-dev/runtime-stage/stage-app-manager/store-compiled"
# The first egress-capable pilot is intentionally exact-ID and exact-tag
# restricted, not a generic "enable the internet for the entire store" switch.
EGRESS_PILOT_ID="default:MySpeed"
EGRESS_PILOT_IMAGE="germannewsmaker/myspeed:1.0.8"

def _outbound_pilot(app_id, doc, plan):
    if app_id!=EGRESS_PILOT_ID or len(plan["services"])!=1:
        return False
    if len(doc.get("services",{}))!=1 or "myspeed" not in doc["services"]:
        return False
    source=doc["services"]["myspeed"]
    return (source.get("image")==EGRESS_PILOT_IMAGE
            and source.get("network_mode")=="bridge"
            and plan["services"][0]["name"]=="myspeed")


def resolve_image(source, run=None):
    if not isinstance(source,str) or not IMAGE.fullmatch(source):
        raise AppError("unsupported_catalog_image",409)
    if run is None:
        def run(args):
            return subprocess.run(args,check=False,capture_output=True,text=True,timeout=12)
    try:
        p=run(["docker","image","inspect","--format","{{.Id}}",source])
    except (OSError,subprocess.TimeoutExpired):
        return None
    if p.returncode:
        return None
    candidate=p.stdout.strip()
    return candidate if DIGEST.fullmatch(candidate) else None

def prepare_images(app_id):
    """Explicit operator preparation of exact catalogue images into Docker cache.

    No Compose execution or original volumes; future installs use sha256 IDs.
    Disk/cache mutations here never start or replace production containers.
    """
    _,doc=_find_catalog_definition(app_id)
    plan=analyze(doc,app_id=app_id)
    missing=sorted({part["image"] for part in plan["services"]
                    if part["immutable_image"] is None})
    if not missing:
        return {"operation":"already_cached","app_id":app_id,
                "prepared_images":0,"production_mutation_allowed":False}
    try:
        if shutil.disk_usage("/var/lib/docker").free < 8*1024**3:
            raise AppError("insufficient_safe_docker_disk_headroom",409)
    except OSError:
        raise AppError("docker_cache_disk_unavailable",503)
    def run(*args,timeout=180):
        try:
            proc=subprocess.run(("docker",*args),capture_output=True,
                                text=True,check=False,timeout=timeout)
        except (OSError,subprocess.TimeoutExpired):
            raise AppError("store_image_preparation_unavailable",503)
        if proc.returncode:
            raise AppError("store_image_preparation_failed",503)
        return proc.stdout.strip()
    for source in missing:
        # Pull only an image named by the existing CasaOS metadata,
        # never a repository or arbitrary URL supplied by an API client.
        run("pull",source,timeout=240)
        size=run("image","inspect","--format","{{.Size}}",source,timeout=15)
        try: n=int(size)
        except ValueError:
            raise AppError("invalid_prepared_image_size",409)
        if not 0<n<=1_000_000_000:
            raise AppError("prepared_image_exceeds_staging_size_limit",409)
        if not resolve_image(source):
            raise AppError("prepared_image_identity_unavailable",409)
    return {"operation":"prepared","app_id":app_id,
            "prepared_images":len(missing),
            "production_mutation_allowed":False}

def dependencies(service):
    source=service.get("depends_on") or []
    if isinstance(source,list):
        deps=source
    elif isinstance(source,dict):
        deps=list(source)
        # Preserve completed-successfully dependencies for one-shot init
        # services. Runtime requires an exact successful exit status.
        if not all(isinstance(v,dict) and v.get("condition","service_started")
                   in ("service_started","service_healthy","service_completed_successfully")
                   for v in source.values()):
            raise AppError("invalid_catalog_dependency",409)
    else:
        raise AppError("invalid_catalog_dependency",409)
    if not all(isinstance(n,str) and NAME.fullmatch(n) for n in deps):
        raise AppError("invalid_catalog_dependency",409)
    return deps

def catalog_tcp_port(service):
    """Extract only an app's declared TCP target, never its original host port."""
    ports=service.get("ports") or []
    if not isinstance(ports,list):
        return None
    for port in ports:
        raw=None
        if isinstance(port,int) and type(port) is int:
            raw=str(port)
        elif isinstance(port,str):
            raw=port.strip().rsplit(":",1)[-1]
        elif isinstance(port,dict) and port.get("protocol","tcp")=="tcp":
            raw=str(port.get("target",""))
        if raw is None or not re.fullmatch(r"[0-9]{1,5}(?:/tcp)?",raw):
            continue
        n=int(raw.split("/")[0])
        if 1<=n<=65535:
            return n
    return None

def analyze(doc, resolver=resolve_image, *, app_id=None):
    if not isinstance(doc,dict) or not isinstance(doc.get("services"),dict):
        raise AppError("invalid_catalog_compose",409)
    source=doc["services"]
    if not 1<=len(source)<=MAX_SERVICES:
        raise AppError("unsupported_catalog_service_count",409)
    specs=[]
    mounts_total=0
    edges={}
    for name,service in sorted(source.items()):
        if not isinstance(name,str) or not NAME.fullmatch(name) or not isinstance(service,dict):
            raise AppError("invalid_catalog_service",409)
        image=service.get("image")
        if not isinstance(image,str) or not IMAGE.fullmatch(image):
            raise AppError("invalid_catalog_image",409)
        brokered=host_socket_eligible(app_id,doc) and name==host_socket_service(app_id)
        sandbox_service=(host_socket_adapted(app_id,doc,name,service)
                         if brokered else service)
        targets=_mount_targets(sandbox_service)
        mounts_total+=len(targets)+(1 if brokered else 0)
        if mounts_total>MAX_TOTAL_MOUNTS:
            raise AppError("too_many_catalog_mounts",409)
        deps=dependencies(service)
        if len(deps)!=len(set(deps)):
            raise AppError("duplicate_catalog_dependencies",409)
        edges[name]=deps
        specs.append({"name":name,"image":image,"immutable_image":resolver(image),
                      "mount_targets":targets,
                      "read_only_targets":sorted(_read_only_targets(sandbox_service) & set(targets)),
                      "host_socket_adapter":brokered,
                      "depends_on":deps,
                      "dependency_conditions":{dep:((service.get("depends_on") or {}).get(dep,{}).get(
                          "condition","service_started") if isinstance(service.get("depends_on"),dict)
                          else "service_started") for dep in deps},
                      "web_target":catalog_tcp_port(service)})
    if any(dep not in edges or dep==name for name,ds in edges.items() for dep in ds):
        raise AppError("missing_or_self_catalog_dependency",409)
    required={}
    for spec in specs:
        for dep,condition in spec["dependency_conditions"].items():
            required.setdefault(dep,set()).add(condition)
    if any("service_completed_successfully" in cs and len(cs)>1
           for cs in required.values()):
        raise AppError("conflicting_catalog_one_shot_dependency",409)
    visiting=set()
    visited=set()
    order=[]
    def visit(name):
        if name in visiting:raise AppError("cyclic_catalog_dependency",409)
        if name in visited:return
        visiting.add(name)
        for dep in edges[name]:visit(dep)
        visiting.remove(name)
        visited.add(name)
        order.append(name)
    for name in sorted(edges):visit(name)
    completed_init=sorted({dep for spec in specs
                           for dep,condition in spec["dependency_conditions"].items()
                           if condition=="service_completed_successfully"})
    return {"services":specs,"startup_order":order,"volume_count":mounts_total,
            "one_shot_init_services":completed_init,
            "cached_image_count":sum(s["immutable_image"] is not None for s in specs),
            "all_images_cached":all(s["immutable_image"] is not None for s in specs),
            "staging_only":True,"production_mutation_allowed":False}

def preview(app_id):
    known,doc=_find_catalog_definition(app_id)
    plan=analyze(doc,app_id=app_id)
    return {"id":app_id,"title":known["title"],
            "outbound_network_pilot":_outbound_pilot(app_id,doc,plan),
            "service_count":len(plan["services"]),
            "startup_order":plan["startup_order"],
            "one_shot_init_services":plan["one_shot_init_services"],
            "stage_volume_count":plan["volume_count"],
            "cached_immutable_images":plan["cached_image_count"],
            "all_images_cached":plan["all_images_cached"],
            "sandbox_plan_supported":True,
            "original_ports_env_and_bind_sources_discarded":True,
            "application_functionality_verified":False,
            "production_mutation_allowed":False,
            "nextcloud_user_data_inspected":False,
            "migration_allowed":False}

def compile_stage(project, app_id, host_port=None):
    if not re.fullmatch(r"osd-compiled-[0-9a-f]{12}\Z",project):
        raise AppError("invalid_compiler_project",400)
    _,doc=_find_catalog_definition(app_id)
    plan=analyze(doc,app_id=app_id)
    if not plan["all_images_cached"]:
        raise AppError("one_or_more_images_not_cached",409)
    outbound=_outbound_pilot(app_id,doc,plan)
    qui=qui_supported(app_id,doc)
    if app_id==QUI_APP and not qui:
        raise AppError("qui_catalog_pilot_revision_unsupported",409)
    qui_env=qui_environments(project) if qui else {}
    network="egress" if outbound else "isolated"
    services={}
    published=False
    for spec in plan["services"]:
        name=spec["name"]
        volumes=[]
        for i,target in enumerate(spec["mount_targets"]):
            mount={
                "type":"bind","source":f"{STAGE}/{project}/{name}/volume-{i}",
                "target":target,"bind":{"create_host_path":False},
            }
            if target in spec["read_only_targets"]:
                mount["read_only"]=True
            volumes.append(mount)
        if spec["host_socket_adapter"]:
            volumes.append(host_socket_mount())
        result={
            "image":spec["immutable_image"],"pull_policy":"never",
            "networks":[network],"cap_drop":["ALL"],
            "security_opt":["no-new-privileges:true"],
            "user":"1000:1000","pids_limit":64,"mem_limit":"256m",
            "restart":"no",
            "volumes":volumes,
            "labels":{"osd.m1.compiled":"staging-only",
                      "osd.m1.compiled.project":project,
                      "osd.m1.compiled.service":name,
                      "osd.m1.compiled.app":app_id},
        }
        if spec["host_socket_adapter"]:
            result["labels"][HOST_SOCKET_LABEL]=HOST_SOCKET_LABEL_VALUE
        if qui:
            result["environment"]=qui_env[name]
            if name=="postgres":
                result["healthcheck"]=QUI_HEALTH
        if spec["depends_on"]:
            conditions=spec["dependency_conditions"]
            if any(c in ("service_healthy","service_completed_successfully") for c in conditions.values()):
                result["depends_on"]={name:{"condition":conditions[name]}
                                      for name in sorted(conditions)}
            else:
                result["depends_on"]=sorted(spec["depends_on"])
        if spec["web_target"] is not None and host_port is not None and not published:
            if type(host_port) is not int or not 18720<=host_port<=19999:
                raise AppError("invalid_stage_web_port",400)
            result["ports"]=[f"127.0.0.1:{host_port}:{spec['web_target']}"]
            published=True
        services[name]=result
    return {"name":project,"services":services,
            "networks":({"egress":{"driver":"bridge","internal":False}}
                        if outbound else {"isolated":{"internal":True}})}
