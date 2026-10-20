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
from stage_apps import AppError

_cache_lock=threading.Lock()
_cached=None
_expiration=0.0
SOURCE_OPTIONS=(
    "environment","env_file","ports","network_mode","networks",
    "privileged","devices","cap_add","cap_drop","command","entrypoint",
    "user","restart","deploy","healthcheck","extra_hosts","dns","pid","ipc",
    "security_opt")


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
                "feature_gaps":[],"digest_pinned":False}
    try:
        with path.open("r",encoding="utf-8") as handle:
            doc=yaml.load(handle,Loader=SAFE_LOADER)
        plan=analyze(doc,resolver=lambda source:None)
        services=doc["services"]
        gaps=sorted({option for spec in services.values()
                     for option in SOURCE_OPTIONS if option in spec})
        if any(spec.get("volumes") for spec in services.values()):
            gaps.append("original_volume_sources")
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
                "feature_gaps":sorted(set(gaps)),
                "digest_pinned":all("@sha256:" in image for image in images)}
    except AppError as err:
        return {"id":item["id"],"sandbox_plan_supported":False,
                "reason":err.message,"feature_gaps":[],"digest_pinned":False}
    except (ValueError,TypeError,UnicodeError,yaml.YAMLError):
        return {"id":item["id"],"sandbox_plan_supported":False,
                "reason":"invalid_casaos_store_metadata","feature_gaps":[],
                "digest_pinned":False}


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
