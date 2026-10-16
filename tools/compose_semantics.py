#!/usr/bin/env python3
"""Safe, NO-EXEC Compose capability parser for CasaOS-to-OSD migration.

Examines YAML schema keys, not values of credentials, upload directories,
user bind mounts or .env files. Never executes Docker or Compose. Reports
structured compatibility blockers without leaking configuration secrets.
"""
from __future__ import annotations
import collections
import json
from pathlib import Path

SAFE_KEYS = frozenset({"image","command","entrypoint","working_dir","user",
    "read_only","restart","stop_grace_period","tty","stdin_open",
    "environment","env_file","labels","hostname","container_name",
    "depends_on","healthcheck","ports","expose","volumes","networks",
    "network_mode","dns","dns_search","extra_hosts","cap_drop","cap_add",
    "privileged","devices","security_opt","pid","ipc","ulimits",
    "mem_limit","mem_reservation","cpus","cpu_shares","pids_limit",
    "logging","deploy","init","userns_mode","sysctls","tmpfs",
    "secrets","configs","build","profiles","pull_policy"})
CONDITIONS = {"service_started","service_healthy","service_completed_successfully"}
FORBIDDEN_SAFE_REPLAY = frozenset({
    "privileged","devices","cap_add","pid","ipc","network_mode",
    "ports","volumes","secrets","configs","build","env_file",
    "environment","extra_hosts","security_opt",
})

def assess_config(doc):
    if not isinstance(doc,dict):
        raise ValueError("invalid Compose object")
    services=doc.get("services")
    if not isinstance(services,dict) or not services or len(services)>80:
        raise ValueError("invalid Compose services")
    result=[]
    unresolved=collections.Counter()
    unsafe=collections.Counter()
    names=set(services)
    for name,entry in sorted(services.items()):
        if not isinstance(name,str) or not name or not isinstance(entry,dict):
            raise ValueError("invalid service definition")
        keys=set(entry)
        unknown=sorted(keys-SAFE_KEYS)
        unsafe_keys=sorted(keys&FORBIDDEN_SAFE_REPLAY)
        dep=entry.get("depends_on")
        dep_names=[]
        invalid_conditions=0
        if isinstance(dep,list):
            dep_names=dep
        elif isinstance(dep,dict):
            dep_names=list(dep)
            for option in dep.values():
                if isinstance(option,dict) and option.get("condition","service_started") not in CONDITIONS:
                    invalid_conditions+=1
        elif dep is not None:
            raise ValueError("unknown depends_on structure")
        if any(not isinstance(x,str) or x not in names for x in dep_names):
            raise ValueError("missing or malformed Compose service dependency")
        if name in dep_names:
            raise ValueError("self-dependent Compose service")
        unresolved.update(unknown)
        unsafe.update(unsafe_keys)
        result.append({
            "service_key_count":len(keys),
            "unknown_feature_count":len(unknown),
            "sandbox_replay_restricted_feature_count":len(unsafe_keys),
            "internal_dependency_count":len(dep_names),
            "invalid_dependency_conditions":invalid_conditions,
        })
    # Only counts and generic, enum-like field NAMES leave this parser.
    # No user file paths, port values, env var keys or secrets.
    return {
        "schema":"OSD_COMPOSE_SEMANTICS_V1",
        "service_count":len(result),
        "service_key_total":sum(r["service_key_count"] for r in result),
        "service_dependencies":sum(r["internal_dependency_count"] for r in result),
        "unknown_compose_field_kinds":dict(sorted(unresolved.items())),
        "sandbox_replay_restricted_field_kinds":dict(sorted(unsafe.items())),
        "invalid_dependency_conditions":sum(r["invalid_dependency_conditions"] for r in result),
        "runtime_parity_verified":False,
        "production_modified":False,
        "external_user_data_read":False,
        "synthetic_replay_only":True,
    }

def catalog():
    from acceptance_m1_compose_compat import CONFIG,safe_project_config
    if not CONFIG.is_dir() or CONFIG.is_symlink():
        raise ValueError("CasaOS configuration unavailable")
    count=0
    combined=collections.Counter()
    risky=collections.Counter()
    deps=0
    for candidate in sorted(CONFIG.iterdir()):
        if candidate.is_symlink() or not candidate.is_dir():
            continue
        definition=candidate/"docker-compose.yml"
        if definition.is_symlink() or not definition.is_file():
            continue
        obj=assess_config(safe_project_config(definition))
        count+=1
        combined.update(obj["unknown_compose_field_kinds"])
        risky.update(obj["sandbox_replay_restricted_field_kinds"])
        deps+=obj["service_dependencies"]
    return {"source":"CASAOS_PLATFORM_COMPOSE_FILES_ONLY",
            "app_definitions":count,
            "dependency_edges":deps,
            "unrecognized_feature_kinds":dict(sorted(combined.items())),
            "restricted_for_isolated_replay":dict(sorted(risky.items())),
            "real_app_imports_verified":0,
            "replacement_parity_passed":False,
            "user_uploads_read":False,
            "production_modified":False}

if __name__=="__main__":
    print(json.dumps(catalog(),sort_keys=True))
