"""Read-only CasaOS App Store sandbox planning matrix.

Never reads user data, executes Docker, or exposes secrets or source paths.
"""
from __future__ import annotations
import stat
import threading
import time
import yaml
from casaos_appstore import _index, STORE_ROOT, SAFE_LOADER, MAX_COMPOSE_BYTES
from stage_store_compiler import analyze
from stage_store_general import _read_only_targets
from stage_host_socket import (
    eligible as host_socket_eligible,GLANCES_ID,WUD_ID,HOMEPAGE_ID,
)
from stage_apps import AppError

_cache_lock=threading.Lock()
_cached=None
_expiration=0.0
SOURCE_OPTIONS=(
    "environment","env_file","ports","network_mode","networks",
    "privileged","devices","cap_add","cap_drop","command","entrypoint",
    "user","restart","deploy","healthcheck","extra_hosts","dns","pid","ipc",
    "security_opt")


def _host_requirements(doc):
    """Classify unavailable host integrations, never reveal bind SOURCE paths.

    These are informational labels, not permission grants or install flags.
    An absent integration cannot be silently emulated by an empty volume.
    """
    needed=set()
    services=doc.get("services") if isinstance(doc,dict) else None
    if not isinstance(services,dict):
        return []
    for spec in services.values():
        if not isinstance(spec,dict):
            continue
        for volume in spec.get("volumes",[]) or []:
            target=None
            if isinstance(volume,str):
                parts=volume.split(":")
                if len(parts)>=2:target=parts[1]
            elif isinstance(volume,dict):
                target=volume.get("target")
            if not isinstance(target,str):
                continue
            target=target.rstrip("/")
            if ("docker.sock" in target or target.startswith(
                  ("/var/lib/docker","/var/lib/containerd","/var/lib/casaos"))):
                needed.add("host_docker_or_casaos_api")
            elif target.startswith(("/dev","/run/udev","/sys")):
                needed.add("host_devices_or_kernel")
            elif target.startswith(("/run","/var/run")):
                needed.add("host_system_services")
            elif target.startswith(("/proc","/etc/ssh","/etc/ssl",
                                    "/etc/pki","/root/.ssh","/root/.docker")):
                needed.add("host_security_or_system_files")
            else:
                needed.add("unsupported_volume_declaration")
        if spec.get("depends_on"):
            deps=spec["depends_on"]
            if isinstance(deps,dict) and any(
                isinstance(cond,dict) and
                cond.get("condition")=="service_completed_successfully"
                for cond in deps.values()
            ):
                needed.add("one_shot_init_service")
    return sorted(needed)


def _remediation(doc,error):
    """Non-sensitive corrective hint; never return a host source path.

    Long-form :ro target errors cannot be imported automatically because
    the original mount source might be protected production data.
    """
    services=doc.get("services") if isinstance(doc,dict) else None
    if not isinstance(services,dict):
        return "review_original_compose_metadata"
    targets=[]
    for spec in services.values():
        if not isinstance(spec,dict):
            continue
        for volume in spec.get("volumes",[]) or []:
            if isinstance(volume,dict):
                target=volume.get("target")
                if isinstance(target,str) and target.endswith(":ro"):
                    return "correct_long_form_readonly_target"
                targets.append(target)
            elif isinstance(volume,str) and ":" in volume:
                targets.append(volume.split(":")[1])
    if "/etc/resolv.conf" in targets:
        return "requires_host_dns_and_network_capabilities"
    if error.message in ("unsafe_container_volume_target",
                         "unsupported_volume_type"):
        return "review_original_mounts_without_host_data"
    return "review_unsupported_compose_settings"


def _evaluate(item, evidence):
    path,dev,ino,size,mtime,ctime=evidence
    st=path.lstat()
    if (not stat.S_ISREG(st.st_mode) or
        (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)!=
            (dev,ino,size,mtime,ctime)):
        raise ValueError("catalogue metadata changed during read")
    if st.st_size>MAX_COMPOSE_BYTES:
        return {"id":item["id"],"sandbox_plan_supported":False,
                "reason":"catalog_metadata_exceeds_limits",
                "install_mode":"unsupported_compose_metadata",
                "requirements":[],
                "feature_gaps":[],"digest_pinned":False}
    try:
        with path.open("r",encoding="utf-8") as handle:
            doc=yaml.load(handle,Loader=SAFE_LOADER)
        plan=analyze(doc,resolver=lambda source:None,app_id=item["id"])
        brokered=host_socket_eligible(item["id"],doc)
        services=doc["services"]
        gaps=sorted({option for spec in services.values()
                     for option in SOURCE_OPTIONS if option in spec})
        if brokered:
            gaps.extend(("original_host_docker_socket_never_mounted",
                         "stage_only_readonly_docker_facade",
                         "stage_log_history_and_event_stream_bounded"))
            if item["id"]==GLANCES_ID:
                gaps.extend(("host_pid_namespace_discarded",
                             "host_process_metrics_not_available",
                             "stage_container_metrics_only"))
            if item["id"]==WUD_ID:
                gaps.extend(("external_registry_update_checks_unavailable",
                             "no_production_container_inventory",
                             "stage_only_readonly_container_monitoring"))
            if item["id"]==HOMEPAGE_ID:
                gaps.extend(("original_dashboard_config_not_imported",
                             "original_host_docker_inventory_unavailable",
                             "empty_stage_owned_config_only"))
        if any(spec.get("volumes") for spec in services.values()):
            gaps.append("original_volume_sources")
        if any(_read_only_targets(spec) for spec in services.values()):
            gaps.append("readonly_source_content_not_imported")
        original_volumes=[
            volume for spec in services.values()
            for volume in (spec.get("volumes") or [])
        ]
        if any(
            (volume.get("target") if isinstance(volume,dict) else
             volume.split(":")[1] if isinstance(volume,str) and ":" in volume
             else None) in ("/etc/localtime","/etc/timezone")
            for volume in original_volumes
        ):
            gaps.append("host_timezone_file_mounts_discarded")
        images=[part["image"] for part in plan["services"]]
        return {"id":item["id"],"sandbox_plan_supported":True,
                "reason":"isolated_staging_plan_available",
                "install_mode":"isolated_stage_sandbox",
                "requirements":[],
                "feature_gaps":sorted(set(gaps)),
                "digest_pinned":all("@sha256:" in image for image in images)}
    except AppError as err:
        requirements=_host_requirements(doc)
        resolution=_remediation(doc,err)
        if resolution=="requires_host_dns_and_network_capabilities":
            requirements=sorted(set(requirements+["host_dns_and_network"]))
        host_restricted=any(value not in (
            "unsupported_volume_declaration","one_shot_init_service")
            for value in requirements)
        mode=("special_host_integration" if host_restricted
              else "unsupported_compose_metadata")
        return {"id":item["id"],"sandbox_plan_supported":False,
                "reason":err.message,"install_mode":mode,
                "requirements":requirements,
                "remediation_code":resolution,
                "feature_gaps":[],"digest_pinned":False}
    except (ValueError,TypeError,UnicodeError,yaml.YAMLError):
        return {"id":item["id"],"sandbox_plan_supported":False,
                "reason":"invalid_casaos_store_metadata",
                "install_mode":"unsupported_compose_metadata",
                "requirements":[],
                "feature_gaps":[],"digest_pinned":False}


def listing():
    global _cached,_expiration
    with _cache_lock:
        if _cached is not None and time.monotonic()<_expiration:
            return _cached
        index,paths=_index(STORE_ROOT,with_paths=True)
        rows=[_evaluate(item,paths[item["id"]]) for item in index["apps"]]
        supported=sum(item["sandbox_plan_supported"] for item in rows)
        digest=sum(item["sandbox_plan_supported"] and item["digest_pinned"] for item in rows)
        result={
            "scope":"sanitized_local_casaos_appstore_sandbox_plans",
            "install_mode_counts":{
                mode:sum(row["install_mode"]==mode for row in rows)
                for mode in ("isolated_stage_sandbox",
                             "special_host_integration",
                             "unsupported_compose_metadata")},
            "app_count":len(rows),"sandbox_plan_supported":supported,
            "sandbox_plan_blocked":len(rows)-supported,
            "supported_with_all_images_digest_pinned":digest,
            "source_feature_stripping_disclosed":True,
            "runtime_compatibility_proven":False,
            "production_equivalence_proven":False,
            "production_mutation_allowed":False,
            "nextcloud_user_data_inspected":False,
            "apps":rows,
        }
        _cached=result
        _expiration=time.monotonic()+90
        return result
