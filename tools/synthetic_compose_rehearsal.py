#!/usr/bin/env python3
"""Compile *structural* CasaOS Compose fixtures, never original app workloads.

All source image, command, credentials, environment, ports, mounts, paths,
capabilities and networks are thrown away. Only service count and validated
depends_on relationships can inform generated isolated BusyBox fixtures.
Docker Compose config validation only; no containers are created here.
"""
from __future__ import annotations

import json
import re
import secrets
import subprocess
import tempfile
from pathlib import Path
from acceptance_m1_compose_compat import CONFIG, safe_project_config
from compose_semantics import assess_config

OUTPUT_ROOT = Path("/opt/openserverdesk-dev/runtime-stage")
SERVICE_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}\Z")


def synthetic(doc):
    summary = assess_config(doc)
    services = doc["services"]
    if len(services) > 80 or not all(SERVICE_ID.fullmatch(s) for s in services):
        raise ValueError("invalid source service identifiers")
    clean = {}
    for name, definition in sorted(services.items()):
        depends = definition.get("depends_on") or []
        if isinstance(depends, dict):
            depends = list(depends)
        if not isinstance(depends, list) or any(
                not isinstance(dep, str) or dep not in services for dep in depends):
            raise ValueError("invalid service references")
        clean[name] = {
            "image": "busybox:latest",
            "pull_policy": "never",
            "command": ["sleep", "60"],
            "network_mode": "none",
            "read_only": True,
            "user": "1000:1000",
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "pids_limit": 16,
            "mem_limit": "32m",
            "restart": "no",
        }
        if depends:
            clean[name]["depends_on"] = sorted(depends)
    return {"name": "osd-m1-synthetic",
            "services": clean}, summary


def verify_fixture(config: dict):
    with tempfile.TemporaryDirectory(prefix="osd-synthetic-compose-",dir=OUTPUT_ROOT) as tmp:
        path = Path(tmp)/"compose.json"
        path.write_text(json.dumps(config,sort_keys=True)+"\n")
        # The exact generated config has no bind paths or source secrets.
        command = ["docker", "compose", "-f", str(path), "config", "--quiet"]
        result = subprocess.run(command,capture_output=True,text=True,timeout=20)
        if result.returncode:
            raise ValueError("synthetic Compose semantic validation failed")



def execute_isolated(doc):
    """Run only generated BusyBox fixtures in a unique staging Compose project.

    This never replays source images, binds, ports, secrets, or env. A unique
    project name prevents touching any existing Compose application.
    """
    config, _ = synthetic(doc)
    project = "osd-m1-fixture-" + secrets.token_hex(6)
    with tempfile.TemporaryDirectory(prefix="osd-exec-", dir=OUTPUT_ROOT) as tmp:
        path = Path(tmp) / "compose.json"
        path.write_text(json.dumps(config, sort_keys=True) + "\n")
        base = ["docker", "compose", "-p", project, "-f", str(path)]
        started = False
        try:
            up = subprocess.run(base + ["up", "-d", "--no-build", "--pull", "never"],
                                capture_output=True, text=True, timeout=75)
            if up.returncode:
                raise RuntimeError("isolated synthetic Compose startup failed")
            started = True
            ps = subprocess.run(base + ["ps", "--status", "running", "--services"],
                                capture_output=True, text=True, timeout=20)
            if ps.returncode or set(ps.stdout.splitlines()) != set(config["services"]):
                raise RuntimeError("isolated synthetic services not all running")
            return {"scope": "SYNTHETIC_COMPOSE_EXECUTION_ONLY",
                    "synthetic_services_running": len(config["services"]),
                    "real_app_imports_verified": 0,
                    "production_modified": False}
        finally:
            # Cleanup even after a partial 'up' failure; the unique project
            # cannot match a pre-existing production Compose project.
            subprocess.run(base + ["down", "--remove-orphans"],
                           capture_output=True, text=True, timeout=40)

def check_casaos():
    if not CONFIG.is_dir() or CONFIG.is_symlink():
        raise ValueError("CasaOS platform configuration unavailable")
    total = 0
    service_count = 0
    failed = 0
    for child in sorted(CONFIG.iterdir()):
        if child.is_symlink() or not child.is_dir():
            continue
        f = child/"docker-compose.yml"
        if f.is_symlink() or not f.is_file():
            continue
        doc = safe_project_config(f)
        replay, analysis = synthetic(doc)
        total += 1
        service_count += analysis["service_count"]
        try:
            verify_fixture(replay)
        except (ValueError, OSError, subprocess.TimeoutExpired):
            failed += 1
    return {
        "scope":"SYNTHETIC_COMPOSE_STRUCTURE_ONLY",
        "source_definitions":total,
        "source_services":service_count,
        "synthetic_compose_config_accepted":total-failed,
        "synthetic_compose_config_rejected":failed,
        "real_app_imports_verified":0,
        "production_equivalence_proven":False,
        "actual_source_images_executed":False,
        "original_ports_published":False,
        "original_bind_data_accessed":False,
        "nextcloud_uploads_opened":False,
        "production_modified":False,
    }

if __name__=="__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-isolated-demo", action="store_true",
                        help="run and clean up two synthetic staging services only")
    args = parser.parse_args()
    if args.run_isolated_demo:
        fixture = {"services": {"database": {"image": "discarded"},
                   "frontend": {"image": "discarded",
                                "depends_on": ["database"]}}}
        print(json.dumps(execute_isolated(fixture), sort_keys=True))
    else:
        print(json.dumps(check_casaos(),sort_keys=True))
