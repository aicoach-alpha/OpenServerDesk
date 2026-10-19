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
from compose_semantics import assess_config, isolated_deployment_plan

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
            "networks": ["fixture_internal"],
            "read_only": True,
            "tmpfs": ["/fixture-data:rw,noexec,nosuid,size=1m"],
            "volumes": [f"fixture_{name}:/fixture-persistent"],
            "environment": {"OSD_FIXTURE_MODE": "synthetic"},
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
            "services": clean,
            "networks": {"fixture_internal": {"internal": True}},
            "volumes": {f"fixture_{name}": {} for name in clean}}, summary


def verify_fixture(config: dict):
    with tempfile.TemporaryDirectory(prefix="osd-synthetic-compose-",dir=OUTPUT_ROOT) as tmp:
        path = Path(tmp)/"compose.json"
        path.write_text(json.dumps(config,sort_keys=True)+"\n")
        # The exact generated config has no bind paths or source secrets.
        command = ["docker", "compose", "-f", str(path), "config", "--quiet"]
        result = subprocess.run(command,capture_output=True,text=True,timeout=20)
        if result.returncode:
            raise ValueError("synthetic Compose semantic validation failed")




def translate_stage_resources(doc):
    """Replace source resource declarations with isolated, value-free fixtures.

    Never copy source env values, port numbers, mount paths, or images.
    Unsupported source features remain blocked by the strict planner.
    """
    safe = {"image", "depends_on", "ports", "environment", "volumes",
            "container_name", "hostname", "cpu_shares", "deploy",
            "restart", "labels", "mem_limit", "pids_limit", "pull_policy"}
    result = {"services": {}}
    counts = {"port_declarations": 0, "environment_declarations": 0,
              "volume_declarations": 0, "discarded_runtime_fields": 0}
    services = doc.get("services")
    if not isinstance(services, dict) or not services:
        raise ValueError("invalid source services")
    for name, cfg in services.items():
        if not isinstance(cfg, dict) or set(cfg) - safe:
            raise ValueError("source features require explicit stage translation")
        out = {"image": "busybox:latest"}
        counts["discarded_runtime_fields"] += len(set(cfg) -
            {"image", "depends_on", "ports", "environment", "volumes"})
        if "depends_on" in cfg:
            out["depends_on"] = cfg["depends_on"]
        for field, counter in (("ports", "port_declarations"),
                               ("volumes", "volume_declarations")):
            values = cfg.get(field, [])
            if not isinstance(values, list):
                raise ValueError("invalid resource declaration")
            counts[counter] += len(values)
        env = cfg.get("environment", {})
        if not isinstance(env, (dict, list)):
            raise ValueError("invalid environment declaration")
        counts["environment_declarations"] += len(env)
        result["services"][name] = out
    isolated_deployment_plan(result)
    return result, counts

def execute_isolated(doc):
    """Run only generated BusyBox fixtures in a unique staging Compose project.

    This never replays source images, binds, ports, secrets, or env. A unique
    project name prevents touching any existing Compose application.
    """
    translated, resource_counts = translate_stage_resources(doc)
    config, _ = synthetic(translated)
    # Source resource values are discarded; only sanitized dependencies remain.
    plan = isolated_deployment_plan(translated)
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
            # Write only synthetic data to each uniquely named stage volume.
            before = subprocess.run(base + ["ps", "-q"], capture_output=True,
                                    text=True, timeout=20)
            if before.returncode or len(before.stdout.splitlines()) != len(config["services"]):
                raise RuntimeError("isolated fixture IDs unavailable before persistence test")
            for cid in before.stdout.splitlines():
                write = subprocess.run(["docker", "exec", "--user", "0:0", cid, "sh", "-c",
                    "printf osd-stage-marker > /fixture-persistent/marker"],
                    capture_output=True, text=True, timeout=20)
                if write.returncode:
                    raise RuntimeError("isolated fixture persistence write failed")
            # Exercise a real lifecycle transition on this unique fixture only.
            stop = subprocess.run(base + ["stop"], capture_output=True,
                                  text=True, timeout=45)
            if stop.returncode:
                raise RuntimeError("isolated fixture stop failed")
            stopped = subprocess.run(base + ["ps", "--status", "running", "--services"],
                                     capture_output=True, text=True, timeout=20)
            if stopped.returncode or stopped.stdout.strip():
                raise RuntimeError("isolated fixture did not stop cleanly")
            restart = subprocess.run(base + ["start"], capture_output=True,
                                     text=True, timeout=45)
            if restart.returncode:
                raise RuntimeError("isolated fixture restart failed")
            resumed = subprocess.run(base + ["ps", "--status", "running", "--services"],
                                     capture_output=True, text=True, timeout=20)
            if resumed.returncode or set(resumed.stdout.splitlines()) != set(config["services"]):
                raise RuntimeError("isolated fixture did not resume")
            # Data survives stop/start without touching any host bind mount.
            after = subprocess.run(base + ["ps", "-q"], capture_output=True,
                                   text=True, timeout=20)
            if after.returncode or len(after.stdout.splitlines()) != len(config["services"]):
                raise RuntimeError("isolated fixture IDs unavailable after restart")
            for cid in after.stdout.splitlines():
                read = subprocess.run(["docker", "exec", cid, "cat",
                    "/fixture-persistent/marker"], capture_output=True,
                    text=True, timeout=20)
                if read.returncode or read.stdout != "osd-stage-marker":
                    raise RuntimeError("isolated fixture persistence did not survive restart")
            # Snapshot, delete, and restore synthetic marker only. The
            # snapshot is inside the ephemeral staging directory, never a
            # source app bind mount or user-data backup.
            for index, cid in enumerate(after.stdout.splitlines()):
                snapshot = Path(tmp) / f"fixture-marker-{index}"
                backup = subprocess.run(["docker", "cp",
                    f"{cid}:/fixture-persistent/marker", str(snapshot)],
                    capture_output=True, text=True, timeout=20)
                if backup.returncode or snapshot.read_bytes() != b"osd-stage-marker":
                    raise RuntimeError("synthetic fixture snapshot failed")
                remove = subprocess.run(["docker", "exec", "--user", "0:0",
                    cid, "rm", "/fixture-persistent/marker"],
                    capture_output=True, text=True, timeout=20)
                if remove.returncode:
                    raise RuntimeError("synthetic fixture marker removal failed")
                restore = subprocess.run(["docker", "cp", str(snapshot),
                    f"{cid}:/fixture-persistent/marker"],
                    capture_output=True, text=True, timeout=20)
                if restore.returncode:
                    raise RuntimeError("synthetic fixture restore failed")
                verify = subprocess.run(["docker", "exec", cid, "cat",
                    "/fixture-persistent/marker"], capture_output=True,
                    text=True, timeout=20)
                if verify.returncode or verify.stdout != "osd-stage-marker":
                    raise RuntimeError("synthetic fixture restored marker mismatch")
            # Verify actual staging resources, not just Compose declarations.
            ids = subprocess.run(base + ["ps", "-q"], capture_output=True,
                                 text=True, timeout=20)
            container_ids = ids.stdout.splitlines()
            if ids.returncode or len(container_ids) != len(config["services"]):
                raise RuntimeError("isolated fixture container IDs unavailable")
            inspected = subprocess.run(
                ["docker", "inspect", "--format",
                 "{{json .HostConfig}}", *container_ids],
                capture_output=True, text=True, timeout=20)
            if inspected.returncode:
                raise RuntimeError("isolated fixture inspection failed")
            for line in inspected.stdout.splitlines():
                host = json.loads(line)
                tmpfs = host.get("Tmpfs") or {}
                if "/fixture-data" not in tmpfs or host.get("ReadonlyRootfs") is not True:
                    raise RuntimeError("isolated fixture storage guard missing")
                if host.get("PortBindings"):
                    raise RuntimeError("isolated fixture unexpectedly published ports")
            return {"scope": "SYNTHETIC_COMPOSE_EXECUTION_ONLY",
                    "synthetic_services_running": len(config["services"]),
                    "dependency_order": plan["service_order"],
                    "isolated_network": True,
                    "ephemeral_tmpfs": True,
                    "runtime_resource_guards_verified": True,
                    "stop_start_lifecycle_verified": True,
                    "synthetic_volume_persistence_verified": True,
                    "synthetic_snapshot_restore_verified": True,
                    "synthetic_environment": True,
                    "translated_resource_counts": resource_counts,
                    "real_app_imports_verified": 0,
                    "production_modified": False}
        finally:
            # Cleanup even after a partial 'up' failure; the unique project
            # cannot match a pre-existing production Compose project.
            subprocess.run(base + ["down", "--remove-orphans", "--volumes"],
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
                                "depends_on": ["database"],
                                "ports": ["9999:80"],
                                "environment": {"SECRET": "discarded"},
                                "volumes": ["/private:/data"],
                                "container_name": "source-name-discarded",
                                "hostname": "source-host-discarded",
                                "cpu_shares": 512,
                                "deploy": {"resources": {"limits": {"memory": "1G"}}}}}}
        print(json.dumps(execute_isolated(fixture), sort_keys=True))
    else:
        print(json.dumps(check_casaos(),sort_keys=True))
