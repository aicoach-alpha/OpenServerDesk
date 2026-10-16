#!/usr/bin/env python3
"""Strict metadata-only CasaOS Compose compatibility baseline.

Reads ONLY CasaOS-controlled Compose YAML files directly below
/var/lib/casaos/apps/<app>/docker-compose.yml; never reads .env, referenced
volumes or bind targets, Nextcloud/HDD user contents, or other files.
"""
from __future__ import annotations
import collections
import datetime as dt
import json
import os
import stat
import tempfile
from pathlib import Path
import yaml

CONFIG = Path("/var/lib/casaos/apps")
STAGE = Path("/opt/openserverdesk-dev/runtime-stage")
PUBLIC = STAGE / "M1_COMPOSE_COMPATIBILITY_PUBLIC.json"
PRIVATE = STAGE / "M1_COMPOSE_COMPATIBILITY_PRIVATE.json"
MAX_APPS = 100
MAX_BYTES = 512000
SAFE_TEMPLATE_SERVICE_KEYS = frozenset({
    "image", "command", "network_mode", "read_only", "user", "cap_drop",
    "security_opt", "mem_limit", "pids_limit", "restart", "labels", "volumes",
    "pull_policy",
})
HIGH_RISK_KEYS = frozenset({
    "privileged", "devices", "pid", "ipc", "uts", "network_mode",
    "cap_add", "security_opt", "ports", "volumes", "secrets", "configs",
    "env_file", "environment", "build", "extends",
})


def safe_project_config(path):
    if not isinstance(path, Path) or not path.name == "docker-compose.yml":
        raise ValueError("not an approved platform Compose definition")
    if path.parent.parent != CONFIG:
        raise ValueError("Compose file is not from the safe platform config folder")
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("symlinked Compose source denied")
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BYTES or st.st_nlink != 1:
        raise ValueError("unsafe Compose configuration source")
    if st.st_dev != CONFIG.stat().st_dev:
        raise ValueError("Compose definition crosses a filesystem mount")
    with path.open("rb") as handle:
        doc = yaml.safe_load(handle.read(MAX_BYTES+1))
    if not isinstance(doc, dict):
        raise ValueError("invalid Compose object")
    services = doc.get("services", {})
    if not isinstance(services, dict) or not services or len(services) > 80:
        raise ValueError("missing/invalid Compose services")
    return doc


def classify(doc):
    services = doc["services"]
    keys = set()
    risky = set()
    apps = 0
    mounts = 0
    exposed_ports = 0
    for name, cfg in services.items():
        if not isinstance(name, str) or not isinstance(cfg, dict):
            raise ValueError("invalid Compose service")
        apps += 1
        keys.update(cfg)
        risky.update(set(cfg) & HIGH_RISK_KEYS)
        volumes = cfg.get("volumes") or []
        if isinstance(volumes, list):
            mounts += len(volumes)
        ports = cfg.get("ports") or []
        if isinstance(ports, list):
            exposed_ports += len(ports)
    # This is conservative: even a stage-allowlisted feature has not passed
    # arbitrary Compose compatibility testing; do not conflate with parity.
    unsupported = sorted(keys-SAFE_TEMPLATE_SERVICE_KEYS)
    return {
        "services":apps,
        "mount_declarations":mounts,
        "port_declarations":exposed_ports,
        "service_schema_keys":sorted(keys),
        "currently_unsupported_service_keys":unsupported,
        "security_sensitive_feature_kinds":sorted(risky),
        "compose_features": sorted(k for k in doc if k != "services"),
        "general_import_runtime_verified":False,
    }


def assess(root=CONFIG):
    if root.is_symlink() or not root.is_dir():
        raise ValueError("CasaOS platform config folder unavailable")
    if root != CONFIG:
        raise ValueError("untrusted CasaOS configuration root")
    children = sorted(
        p for p in root.iterdir()
        if not p.is_symlink() and p.is_dir()
        and not (p/"docker-compose.yml").is_symlink()
        and (p/"docker-compose.yml").is_file()
    )
    if len(children)>MAX_APPS:
        raise ValueError("too many app definitions")
    rows={}
    failures={}
    counts=collections.Counter()
    for p in children:
        path=p/"docker-compose.yml"
        try:
            doc=safe_project_config(path)
            metrics=classify(doc)
            rows[p.name]=metrics
            counts["valid_definitions"]+=1
            counts["service_count"]+=metrics["services"]
            counts["mount_declarations"]+=metrics["mount_declarations"]
            counts["port_declarations"]+=metrics["port_declarations"]
            counts["currently_unsupported_definitions"]+=int(
                bool(metrics["currently_unsupported_service_keys"]))
            counts["general_import_runtime_verified"]+=int(
                metrics["general_import_runtime_verified"])
        except (OSError, ValueError, yaml.YAMLError) as err:
            # Preserve private identifying details in root-only report;
            # never print YAML values or secrets.
            failures[p.name]=type(err).__name__
            counts["invalid_definitions"]+=1
    summary={
        "schema_version":1,
        "scope":"CASAOS_PLATFORM_COMPOSE_YAML_ONLY_NO_USER_DATA",
        "checked_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source_config_definitions":len(children),
        "valid_definitions":counts["valid_definitions"],
        "invalid_definitions":counts["invalid_definitions"],
        "source_services":counts["service_count"],
        "mount_declarations":counts["mount_declarations"],
        "port_declarations":counts["port_declarations"],
        "definitions_needing_additional_compose_support":counts["currently_unsupported_definitions"],
        "generally_importable_apps_e2e_verified":counts["general_import_runtime_verified"],
        "nextcloud_user_files_opened":False,
        "nextcloud_user_data_copied":False,
        "production_modified":False,
        "general_casaos_compose_parity_proven":False,
        "migration_allowed":False,
    }
    return summary, {"public":summary,"applications":rows,"parse_failures":failures}


def publish():
    public,private=assess()
    for path,report,mode in ((PRIVATE,private,0o600),(PUBLIC,public,0o644)):
        if path.is_symlink() or not path.parent.is_dir():
            raise RuntimeError("unexpected report path")
        fd,temp=tempfile.mkstemp(prefix=".compose-compat-",dir=path.parent)
        try:
            with os.fdopen(fd,"w") as handle:
                json.dump(report,handle,sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp,mode)
            os.replace(temp,path)
        finally:
            Path(temp).unlink(missing_ok=True)
    print(json.dumps(public,sort_keys=True))


if __name__=="__main__":
    publish()
