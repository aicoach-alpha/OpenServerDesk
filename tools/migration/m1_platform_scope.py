#!/usr/bin/env python3
"""SAFE migration scope for replacing CasaOS, not user-hosted application data.

Docker metadata is queried from the Engine ONLY; files in protected HDD /
Nextcloud user content roots are never opened, traversed, measured or copied.
Container volumes and data binds remain attached at their original paths.
"""
from __future__ import annotations
import json
import re
import subprocess
from pathlib import Path

# Explicit user boundary. No globbing / walking into these directories.
PROTECTED_DATA_ROOTS = (
    Path("/mnt/data"), Path("/media"), Path("/run/media"),
    Path("/srv/nextcloud/data"), Path("/var/lib/nextcloud/data"),
)
# No wholesale /var/lib/docker (image layers/volumes/Nextcloud uploads).
PLATFORM_CONFIG_ROOTS = (
    Path("/etc/casaos"), Path("/var/lib/casaos"), Path("/etc/docker"),
)
ALLOWED_COMPOSE_PARENTS = (
    Path("/etc/casaos"), Path("/var/lib/casaos"),
    Path("/home/andre"), Path("/opt"), Path("/srv"),
    Path("/mnt/ssd-turbo"),
)
COMPOSE_NAMES = {"docker-compose.yml", "docker-compose.yaml",
                 "compose.yml", "compose.yaml"}
CID = re.compile(r"^[a-f0-9]{64}$")


def under(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def protected(path: Path) -> bool:
    """Decide only from the name, NEVER dereference protected content."""
    if not path.is_absolute() or ".." in path.parts:
        return True
    if any(under(path, root) for root in PROTECTED_DATA_ROOTS):
        return True
    # Future backup must never treat uploaded Nextcloud files as platform config.
    lowered = [v.lower() for v in path.parts]
    if "nextcloud" in lowered and any(
        v in lowered for v in ("data", "uploads", "files", "files_versions",
                               "files_trashbin", "appdata_oc")):
        return True
    if under(path, Path("/mnt")) and not under(path, Path("/mnt/ssd-turbo")):
        return True
    return False


def docker(*args):
    p = subprocess.run(["docker", *args], capture_output=True, text=True,
                       timeout=24)
    if p.returncode:
        raise RuntimeError("Docker metadata inventory not available")
    return p.stdout


def select():
    ids = sorted(set(docker("container", "ls", "--all", "--quiet",
                            "--no-trunc").splitlines()))
    if len(ids) > 10000 or any(not CID.fullmatch(cid) for cid in ids):
        raise RuntimeError("unexpected Docker container identifiers")
    configs = []
    for start in range(0, len(ids), 40):
        batch = ids[start:start+40]
        raw = json.loads(docker("inspect", "--type", "container", *batch))
        if not isinstance(raw, list) or len(raw) != len(batch):
            raise RuntimeError("unexpected Docker metadata")
        configs.extend(raw)
    selected = set()
    for root in PLATFORM_CONFIG_ROOTS:
        if protected(root):
            raise RuntimeError("internal scope policy failure")
        # Touch ONLY the explicitly approved platform config directories.
        if root.is_symlink():
            raise RuntimeError("platform config root is a symlink")
        if root.is_dir():
            # Root itself cannot be an unexpected second mounted filesystem.
            # Do not traverse it (even to inspect the contents).
            if root.stat().st_dev != root.parent.stat().st_dev:
                raise RuntimeError("platform root is a separately mounted filesystem")
            selected.add(str(root))
    skipped_user_data_binds = 0
    all_binds = set()
    compose_projects = set()
    excluded_compose = 0
    running = 0
    writable = 0
    for container in configs:
        if not isinstance(container, dict):
            raise RuntimeError("invalid container metadata")
        state = container.get("State") or {}
        is_running = bool(state.get("Running"))
        running += int(is_running)
        labels = (container.get("Config") or {}).get("Labels") or {}
        if not isinstance(labels, dict):
            labels = {}
        name = labels.get("com.docker.compose.project")
        if isinstance(name, str) and name:
            compose_projects.add(name[:200])
        for entry in container.get("Mounts") or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("RW") and is_running:
                writable += 1
            if entry.get("Type") == "bind":
                value = entry.get("Source")
                if isinstance(value, str):
                    all_binds.add(value)
                    if protected(Path(value)):
                        skipped_user_data_binds += 1
        paths = labels.get("com.docker.compose.project.config_files") or ""
        if not isinstance(paths, str):
            continue
        for part in paths.split(","):
            value = part.strip()
            if not value:
                continue
            p = Path(value)
            if (protected(p) or p.name not in COMPOSE_NAMES or
                    not any(under(p, root) for root in ALLOWED_COMPOSE_PARENTS)):
                excluded_compose += 1
                continue
            # Only chosen Compose files; never walk app bind paths.
            if p.is_symlink():
                raise RuntimeError("Compose path is a symlink")
            if p.is_file():
                selected.add(str(p))
            else:
                excluded_compose += 1
    # One last lexical guard; never stat a protected-data source.
    if not selected or any(protected(Path(x)) for x in selected):
        raise RuntimeError("platform backup scope invalid")
    return {
        "scope": "CASAOS_PLATFORM_CONFIG_ONLY_USER_DATA_PRESERVED",
        "production_modified": False, "migration_allowed": False,
        "container_count": len(configs),
        "running_container_count": running,
        "live_writable_mount_count": writable,
        "compose_project_count": len(compose_projects),
        "unique_bind_source_count": len(all_binds),
        "protected_bind_references_skipped": skipped_user_data_binds,
        "compose_definitions_outside_safe_scope": excluded_compose,
        "external_user_data_copied": False,
        "external_user_data_inspected": False,
        "selected_config_source_count": len(selected),
    }, sorted(selected)


if __name__ == "__main__":
    result, paths = select()
    print(json.dumps({"scope":result["scope"],
                      "selected_config_source_count":len(paths),
                      "container_count":result["container_count"],
                      "compose_project_count":result["compose_project_count"],
                      "protected_bind_references_skipped":result["protected_bind_references_skipped"],
                      "external_user_data_inspected":False,
                      "external_user_data_copied":False,
                      "migration_allowed":False},sort_keys=True))
