#!/usr/bin/env python3
"""Real Docker/Compose data-preservation inventory for M1 migration planning.

ONLY Docker read operations. Does NOT copy, change, stop or restart any
application/volume. Stores potentially sensitive host mount paths in a
private local report, never via the public staging API or GitHub.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from m1_platform_scope import protected

STAGE = Path("/opt/openserverdesk-dev/runtime-stage")
OUTPUT = STAGE / "M1_PRIVATE_APP_DATA_INVENTORY.json"
PUBLIC_SUMMARY = STAGE / "M1_PUBLIC_APP_DATA_SUMMARY.json"
SUMMARY_FIELDS = (
    "checked_at_utc", "container_count", "running_container_count",
    "compose_project_count", "unique_bind_source_count",
    "referenced_named_volume_count", "binds_requiring_operator_review",
    "live_writable_mount_count",
)
CID_RE = re.compile(r"^[0-9a-f]{64}$")
VOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,250}$")


def docker(*args):
    proc = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=30, check=False
    )
    if proc.returncode:
        raise RuntimeError("Docker inspection failed; no state was changed")
    return proc.stdout


def container_ids():
    ids = docker("container", "ls", "--all", "--quiet", "--no-trunc").splitlines()
    if len(ids) > 10000 or not all(CID_RE.fullmatch(x) for x in ids):
        raise RuntimeError("invalid Docker container ID inventory")
    return sorted(set(ids))


def inspect_many(kind, names):
    if not names:
        return []
    result = []
    for start in range(0, len(names), 50):
        objects = json.loads(docker("inspect", "--type", kind, *names[start:start+50]))
        if not isinstance(objects, list) or len(objects) != len(names[start:start+50]):
            raise RuntimeError("unexpected Docker inspect response")
        result.extend(objects)
    return result


def text_value(x, limit=1000):
    return str(x)[:limit] if x is not None else ""


def collect():
    ids = container_ids()
    raw = inspect_many("container", ids)
    containers = []
    sources = {}
    volume_names = set()
    compose_files = {}
    running = 0
    for c in raw:
        cid = c.get("Id", "")
        if cid not in ids:
            raise RuntimeError("Docker inspection identity mismatch")
        config = c.get("Config") or {}
        state = c.get("State") or {}
        labels = config.get("Labels") or {}
        if not isinstance(labels, dict):
            labels = {}
        project = text_value(labels.get("com.docker.compose.project"), 200)
        service = text_value(labels.get("com.docker.compose.service"), 200)
        works = text_value(labels.get("com.docker.compose.project.working_dir"))
        compose_sources = text_value(labels.get("com.docker.compose.project.config_files"))
        if project:
            row = compose_files.setdefault(
                project, {"working_directories": set(), "compose_files": set()}
            )
            if works:
                row["working_directories"].add(works)
            if compose_sources:
                row["compose_files"].update(
                    x.strip() for x in compose_sources.split(",") if x.strip()
                )
        is_running = bool(state.get("Running", False))
        running += int(is_running)
        mounts = []
        for mount in c.get("Mounts") or []:
            kind = mount.get("Type")
            if kind not in ("bind", "volume", "tmpfs", "npipe", "cluster", "image"):
                kind = "unknown"
            source = text_value(mount.get("Source"))
            target = text_value(mount.get("Destination"))
            name = text_value(mount.get("Name"), 256)
            writable = bool(mount.get("RW", False))
            mounts.append({"type": kind, "source": source,
                           "target": target, "name": name, "writable": writable})
            if kind == "volume" and name:
                if not VOL_RE.fullmatch(name):
                    raise RuntimeError("unsafe Docker volume name")
                volume_names.add(name)
            if kind == "bind" and source:
                item = sources.setdefault(
                    source, {"type": "bind", "consumers": [], "exists": None}
                )
                item["consumers"].append({"id":cid[:12], "target":target,
                                          "writable":writable,
                                          "running":is_running})
        containers.append({
            "id": cid[:12], "name": text_value(c.get("Name")).lstrip("/"),
            "image": text_value(config.get("Image")),
            "running": is_running, "compose_project": project,
            "compose_service": service, "mounts": mounts,
        })
    volume_info = inspect_many("volume", sorted(volume_names))
    volumes = []
    for info in volume_info:
        name = info.get("Name")
        if name not in volume_names:
            raise RuntimeError("named volume identity mismatch")
        volumes.append({
            "name": name, "driver": text_value(info.get("Driver"), 100),
            "mountpoint": text_value(info.get("Mountpoint")),
            "consumers": sorted({
                c["name"] for c in containers if any(
                    m["type"] == "volume" and m["name"] == name
                    for m in c["mounts"]
                )
            }),
        })
    for path, item in sources.items():
        p = Path(path)
        # Protected Nextcloud/HDD user data is an opaque EXISTING mount
        # reference. Do not stat, open, traverse or read metadata from it.
        if protected(p):
            item["exists"] = None
            item["symlink"] = None
            item["file_type"] = "preserved_external_user_data_not_inspected"
            item["excluded_from_migration"] = True
            item["requires_operator_review"] = False
            continue
        item["excluded_from_migration"] = False
        # Never dereference untrusted symlinks during planning.
        item["exists"] = p.exists()
        item["symlink"] = p.is_symlink()
        item["file_type"] = (
            "directory" if p.is_dir() else "file" if p.is_file() else "missing_or_other"
        )
        # Bind paths may include sockets that must not be snapshotted.
        item["requires_operator_review"] = (
            item["symlink"] or not item["exists"]
            or str(p).startswith(("/proc/", "/sys/", "/dev/", "/run/", "/var/run/"))
        )
    for group in compose_files.values():
        group["working_directories"] = sorted(group["working_directories"])
        group["compose_files"] = sorted(group["compose_files"])
        group["file_status"] = [
            ({"path": f, "exists": False, "symlink": False,
              "excluded_from_migration": True}
             if protected(Path(f)) else
             {"path": f, "exists": Path(f).is_file(),
              "symlink": Path(f).is_symlink(),
              "excluded_from_migration": False})
            for f in group["compose_files"]
        ]
    unsafe_binds = [p for p, m in sources.items() if m["requires_operator_review"]]
    writable_live = [
        (c["id"], m["target"])
        for c in containers if c["running"] for m in c["mounts"]
        if m["writable"] and m["type"] in ("bind", "volume")
    ]
    return {
        "scope": "READ_ONLY_REAL_DOCKER_APP_DATA_INVENTORY",
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "production_modified": False,
        "migration_allowed": False,
        "requires_quiescence_before_consistent_snapshot": bool(writable_live),
        "container_count": len(containers), "running_container_count": running,
        "compose_project_count": len(compose_files),
        "unique_bind_source_count": len(sources),
        "referenced_named_volume_count": len(volumes),
        "binds_requiring_operator_review": len(unsafe_binds),
        "live_writable_mount_count": len(writable_live),
        "containers": containers, "bind_sources": sources,
        "named_volumes": volumes, "compose_projects": compose_files,
        "blocking_requirements": [
            "No quiesced and consistent real workload backup/restore proof",
            "No verified Compose/project reactivation rollback",
            "No signed production release or final security acceptance",
        ],
    }


def save_private(data):
    if not STAGE.is_dir() or STAGE.is_symlink():
        raise RuntimeError("private stage directory missing/unsafe")
    # Root controls file creation, no private paths are printed or published.
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".m1-app-data-", dir=STAGE)
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(data, f, sort_keys=True, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, OUTPUT)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    # Publish only counted fields without private paths, labels, image names,
    # secrets, container names, volume mountpoints, or environment variables.
    public = {key: data[key] for key in SUMMARY_FIELDS}
    public["migration_allowed"] = False
    public["data_coverage_status"] = "inventory_only_no_quiesced_restore"
    public["production_modified"] = False
    fd, tmpname = tempfile.mkstemp(prefix=".m1-app-summary-", dir=STAGE)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(public, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmpname, 0o644)
        os.replace(tmpname, PUBLIC_SUMMARY)
    finally:
        Path(tmpname).unlink(missing_ok=True)


if __name__ == "__main__":
    report=collect()
    save_private(report)
    print("REAL_APP_DATA_MIGRATION_INVENTORY_COMPLETE")
    for key in (
        "container_count", "running_container_count", "compose_project_count",
        "unique_bind_source_count", "referenced_named_volume_count",
        "binds_requiring_operator_review", "live_writable_mount_count",
    ):
        print(key.upper(), report[key])
    print("MIGRATION_ALLOWED", report["migration_allowed"])
    print("PRIVATE_REPORT", str(OUTPUT))
