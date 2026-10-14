#!/usr/bin/env python3
"""Read-only CasaOS in-place migration compatibility inventory."""
import argparse
import json
import os
import subprocess
from pathlib import Path

SERVICES = ["casaos", "casaos-gateway", "casaos-user-service",
            "casaos-app-management", "casaos-local-storage", "casaos-message-bus"]
PATHS = ["/etc/casaos", "/var/lib/casaos", "/var/lib/casaos/apps",
         "/usr/share/casaos", "/mnt/ssd-turbo", "/mnt/data"]

def run(*args):
    p = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=12)
    return p.returncode, p.stdout.strip()

def inspect():
    version = run("casaos", "-v")[1]
    services = {name: run("systemctl", "is-active", name + ".service")[1] for name in SERVICES}
    paths = {path: {"exists": Path(path).exists(), "mountpoint": os.path.ismount(path)} for path in PATHS}
    _, raw = run("docker", "ps", "-a", "--format", "{{.Names}}")
    containers = sorted(raw.splitlines()) if raw else []
    apps = Path("/var/lib/casaos/apps")
    projects = sorted(d.name for d in apps.iterdir() if d.is_dir() and (d/"docker-compose.yml").is_file()) if apps.is_dir() else []
    checks = {
        "casaos_present": version.startswith("v"),
        "core_services_running": all(x == "active" for x in services.values()),
        "app_config_present": paths["/etc/casaos"]["exists"] and paths["/var/lib/casaos/apps"]["exists"],
        "docker_detected": run("docker", "info", "--format", "{{.ServerVersion}}")[0] == 0,
        "data_hdd_mounted": paths["/mnt/data"]["mountpoint"],
        "ssd_mounted": paths["/mnt/ssd-turbo"]["mountpoint"],
    }
    return {"product":"OpenServerDesk","mode":"READ_ONLY","casaos_version":version,
            "services":services,"path_checks":paths,"container_names":containers,
            "casaos_app_projects":projects,"checks":checks,
            "eligible_for_migration_planning":all(checks.values()),
            "migration_allowed_now":False,
            "reason":"Backup/restore and versioned migration rollback are not yet implemented."}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="")
    a=parser.parse_args()
    result = inspect()
    payload=json.dumps(result, indent=2)
    if a.output:
        Path(a.output).write_text(payload+"\n")
    print(payload)
