"""Safe version choices for ONE stage-owned catalog application.

Only locally cached tags within the installed catalog image repository.
Never accepts arbitrary image URLs, registry changes, image pulls or host
paths. An immutable catalog digest is intentionally not version-switchable.
"""
import json
import re
from stage_apps import AppError
from stage_store_compiler import IMAGE, resolve_image
from stage_store_general import _find_catalog_definition

TAG=re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,89}\Z")
IMMUTABLE=re.compile(r"sha256:[0-9a-f]{64}\Z")


def repository(app_id):
    _,doc=_find_catalog_definition(app_id)
    services=doc.get("services") if isinstance(doc,dict) else None
    if not isinstance(services,dict) or len(services)!=1:
        raise AppError("version_switch_requires_single_service",409)
    service=next(iter(services.values()))
    raw=service.get("image") if isinstance(service,dict) else None
    if not isinstance(raw,str) or not IMAGE.fullmatch(raw) or "@" in raw:
        raise AppError("version_switch_requires_tagged_catalog_image",409)
    leaf=raw.rsplit("/",1)[-1]
    if ":" not in leaf:
        raise AppError("version_switch_requires_tagged_catalog_image",409)
    repo,tag=raw.rsplit(":",1)
    if not repo or not TAG.fullmatch(tag):
        raise AppError("version_switch_requires_tagged_catalog_image",409)
    return repo


def cached_versions(app_id,docker_cmd):
    try:
        repo=repository(app_id)
    except AppError as error:
        if error.message in ("version_switch_requires_single_service",
                             "version_switch_requires_tagged_catalog_image"):
            return []
        raise
    # Only one read-only Docker image metadata operation.
    rows=docker_cmd("image","ls","--format","{{.Repository}}:{{.Tag}}",timeout=20)
    prefix=repo+":"
    choices={line[len(prefix):] for line in rows.splitlines()
             if line.startswith(prefix) and TAG.fullmatch(line[len(prefix):])}
    return sorted(choices)[:32]


def target_image(app_id,tag,resolve=resolve_image):
    repo=repository(app_id)
    if not isinstance(tag,str) or not TAG.fullmatch(tag):
        raise AppError("invalid_stage_image_version",400)
    reference=repo+":"+tag
    if not IMAGE.fullmatch(reference):
        raise AppError("invalid_stage_image_version",400)
    image=resolve(reference)
    if not isinstance(image,str) or not IMMUTABLE.fullmatch(image):
        raise AppError("stage_image_version_not_cached",409)
    return image


def current_tags(app_id,immutable_image,tags,resolve=resolve_image):
    if not IMMUTABLE.fullmatch(str(immutable_image)):
        return []
    repo=repository(app_id)
    return [tag for tag in tags
            if TAG.fullmatch(tag) and
               resolve(repo+":"+tag)==immutable_image]



# The stage runtime forces UID 1000, drops capabilities, and does not import
# original environment. Before stopping a healthy app, reject cached images
# with a different OCI startup contract; those differences require deliberate
# staging adaptation instead of a blind same-repository version switch.
RUNTIME_FIELDS=("User","Entrypoint","Cmd","WorkingDir","Volumes","ExposedPorts")


def _runtime_contract(image_id, docker_cmd):
    if not isinstance(image_id,str) or not IMMUTABLE.fullmatch(image_id):
        raise AppError("invalid_stage_runtime_image",403)
    raw=docker_cmd("image","inspect","--format","{{json .Config}}",image_id)
    if not isinstance(raw,str) or len(raw)>120000:
        raise AppError("stage_image_runtime_metadata_unavailable",503)
    try:
        config=json.loads(raw)
    except (ValueError,TypeError):
        raise AppError("stage_image_runtime_metadata_unavailable",503)
    if not isinstance(config,dict):
        raise AppError("stage_image_runtime_metadata_unavailable",503)
    # Only these startup fields affect the isolated stage launch contract.
    # Image Env values are never exported from this broker.
    return {key:config.get(key) for key in RUNTIME_FIELDS}


def check_runtime_contract(previous_id,next_id,docker_cmd):
    if not all(isinstance(x,str) and IMMUTABLE.fullmatch(x)
               for x in (previous_id,next_id)):
        raise AppError("invalid_stage_runtime_image",403)
    if previous_id==next_id:
        return {"compatible":True,"changed_fields":[]}
    current=_runtime_contract(previous_id,docker_cmd)
    proposed=_runtime_contract(next_id,docker_cmd)
    changed=[key for key in RUNTIME_FIELDS if current[key]!=proposed[key]]
    if changed:
        # Do not expose secret values, only the standard metadata key names.
        raise AppError("stage_image_runtime_contract_incompatible",409)
    return {"compatible":True,"changed_fields":[]}
