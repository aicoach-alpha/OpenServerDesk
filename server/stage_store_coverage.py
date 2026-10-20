"""Read-only installation coverage matrix for all local CasaOS store entries.

No Docker exec, image pull or external user volume lookup. Categories show
code coverage, not successful runtime parity. Source paths and YAML contents
remain private on the NAS.
"""
from __future__ import annotations
from collections import Counter
from pathlib import Path
import yaml
from casaos_appstore import _source_files, _parse, STORE_ROOT, MAX_COMPOSE_BYTES
from stage_store_general import CATALOG_IMAGE_PATTERN, _mount_targets, AppError

REASONS=("eligible_for_isolated_staging","requires_multiservice_engine",
         "advanced_runtime_options","image_tag_not_pinned",
         "unsupported_volume_mapping","invalid_source")
FORBIDDEN=("build","devices","cap_add","pid","ipc","userns_mode",
           "security_opt","extra_hosts","volumes_from","links","extends",
           "entrypoint","command")

def evaluate(doc):
    if not isinstance(doc,dict):
        return "invalid_source"
    services=doc.get("services")
    if not isinstance(services,dict) or not services:
        return "invalid_source"
    if len(services)!=1:
        return "requires_multiservice_engine"
    service=next(iter(services.values()))
    if not isinstance(service,dict):
        return "invalid_source"
    if any(key in service for key in FORBIDDEN):
        return "advanced_runtime_options"
    image=service.get("image")
    if (not isinstance(image,str) or not CATALOG_IMAGE_PATTERN.fullmatch(image)
        or ("@sha256:" not in image and image.rsplit(":",1)[-1].lower()=="latest")):
        return "image_tag_not_pinned"
    try:
        _mount_targets(service)
    except AppError:
        return "unsupported_volume_mapping"
    return "eligible_for_isolated_staging"

def coverage(root=STORE_ROOT):
    counts=Counter()
    stores={}
    total=0
    for namespace,path in _source_files(root):
        total+=1
        reason="invalid_source"
        try:
            if path.lstat().st_size <= MAX_COMPOSE_BYTES:
                with path.open("r",encoding="utf-8") as file:
                    doc=yaml.safe_load(file)
                reason=evaluate(doc)
        except (OSError,UnicodeError,yaml.YAMLError,ValueError):
            pass
        counts[reason]+=1
        breakdown=stores.setdefault(namespace,Counter())
        breakdown[reason]+=1
    assert sum(counts.values())==total
    return {
        "scope":"casaos_local_store_metadata_only",
        "definitions_examined":total,
        "staging_static_eligibility":{name:counts[name] for name in REASONS},
        "store_breakdown":{key:{name:value[name] for name in REASONS}
                           for key,value in sorted(stores.items())},
        "eligible_does_not_imply_app_functionality":True,
        "production_modified":False,
        "external_nextcloud_user_data_inspected":False,
        "production_equivalence_proven":False,
        "migration_allowed":False,
    }
