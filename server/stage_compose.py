"""Staging-only restricted Docker Compose application lifecycle.

A safe-but-real Compose engine: predefined local images, no host published
ports, no network, no privileged/container socket, only stage-owned binds.
Actual CasaOS containers and user data are never targeted for mutation.
"""
from __future__ import annotations
import json
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path

from stage_apps import STAGE, AppError, guarded, registry, persist, inspect_owned

ROOT = STAGE / "compose-projects"
REGISTRY = STAGE / "compose-registry.json"
PROJECT = re.compile(r"osd-m1-compose-[a-f0-9]{12}\Z")
TEMPLATES = {
    "static-web": ("busybox:latest", ["httpd", "-f", "-p", "8080", "-h", "/data"]),
    "task-worker": ("busybox:latest", ["sleep", "86400"]),
}
LIMIT = 4


def _command(*args, timeout=65):
    try:
        proc = subprocess.run(list(args), capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise AppError("isolated_compose_engine_unavailable", 503)
    if proc.returncode or len(proc.stdout) > 100000:
        raise AppError("isolated_compose_command_failed", 503)
    return proc.stdout.strip()


def _root():
    if ROOT.is_symlink():
        raise AppError("unsafe_compose_stage_root", 503)
    if not ROOT.exists():
        ROOT.mkdir(mode=0o700)
    if not ROOT.is_dir() or ROOT.stat().st_mode & 0o077:
        raise AppError("unsafe_compose_stage_root", 503)
    return ROOT


def _project_dir(project):
    if not isinstance(project, str) or not PROJECT.fullmatch(project):
        raise AppError("invalid_compose_project_name", 400)
    path = _root() / project
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise AppError("unsafe_compose_project_directory", 503)
    return path


def _registry():
    if REGISTRY.is_symlink():
        raise AppError("unsafe_compose_registry", 503)
    if not REGISTRY.exists():
        return {}
    try:
        data = json.loads(REGISTRY.read_text())
        if not isinstance(data, dict) or len(data) > LIMIT:
            raise ValueError("bad registry")
        for name, entry in data.items():
            if (not PROJECT.fullmatch(name)
                    or not isinstance(entry, dict)
                    or set(entry) != {"template", "id", "owner"}
                    or entry["template"] not in TEMPLATES
                    or not re.fullmatch(r"[a-f0-9]{64}", entry["id"])
                    or not re.fullmatch(r"[a-f0-9]{32}", entry["owner"])):
                raise ValueError("bad registry item")
        return data
    except (OSError, ValueError, TypeError):
        raise AppError("compose_registry_invalid", 503)


def _save(entries):
    tmp = STAGE / (".compose-registry-" + secrets.token_hex(10))
    try:
        with tmp.open("x") as file:
            json.dump(entries, file, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, REGISTRY)
    finally:
        tmp.unlink(missing_ok=True)


def _compose_content(project, owner, template, data):
    image, command = TEMPLATES[template]
    # JSON is a YAML subset: avoids a YAML serialization dependency. All
    # values are internal constants or regex-enforced stage-owned IDs.
    return json.dumps({
        "name": project,
        "services": {
            "app": {
                "image": image,
                "pull_policy": "never",
                "command": command,
                "network_mode": "none",
                "read_only": True,
                "user": "1000:1000",
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "mem_limit": "64m",
                "pids_limit": 32,
                "restart": "no",
                "labels": {
                    "osd.m1.compose": "stage-only",
                    "osd.m1.compose.owner": owner,
                    "osd.m1.compose.project": project,
                    "osd.m1.compose.template": template,
                },
                "volumes": [{
                    "type": "bind", "source": str(data),
                    "target": "/data", "read_only": True,
                    "bind": {"create_host_path": False},
                }],
            },
        },
    }, sort_keys=True, indent=2) + "\n"


def _inspect(project, entry):
    path = _project_dir(project)
    data = path / "data"
    config = path / "compose.yaml"
    if (path.is_symlink() or data.is_symlink() or config.is_symlink()
            or not path.is_dir() or not data.is_dir() or not config.is_file()):
        raise AppError("compose_project_files_invalid", 503)
    expected = _compose_content(project, entry["owner"], entry["template"], data)
    if config.read_text() != expected:
        raise AppError("compose_project_config_mismatch", 403)
    try:
        obj = json.loads(_command("docker", "inspect", "--type", "container", entry["id"], timeout=20))[0]
    except (ValueError, KeyError, IndexError, TypeError):
        raise AppError("stage_compose_inspection_failed", 503)
    cfg = obj.get("Config") or {}
    host = obj.get("HostConfig") or {}
    labels = cfg.get("Labels") or {}
    mounts = obj.get("Mounts") or []
    if (obj.get("Id") != entry["id"]
            or labels.get("com.docker.compose.project") != project
            or labels.get("com.docker.compose.service") != "app"
            or labels.get("osd.m1.compose") != "stage-only"
            or labels.get("osd.m1.compose.owner") != entry["owner"]
            or labels.get("osd.m1.compose.project") != project
            or labels.get("osd.m1.compose.template") != entry["template"]
            or cfg.get("Image") != TEMPLATES[entry["template"]][0]
            or cfg.get("User") != "1000:1000"
            or host.get("Privileged") is not False
            or host.get("NetworkMode") != "none"
            or host.get("ReadonlyRootfs") is not True
            or host.get("PortBindings")
            or len(mounts) != 1
            or mounts[0].get("Source") != str(data)
            or mounts[0].get("Destination") != "/data"
            or mounts[0].get("RW") is not False):
        raise AppError("stage_compose_provenance_violation", 403)
    state = obj.get("State") or {}
    return {
        "project": project, "template": entry["template"],
        "container_id": entry["id"][:12],
        "running": bool(state.get("Running")),
        "isolated": True, "production_mutation_allowed": False,
    }


def catalog():
    return {"templates": [
        {"id": "static-web", "description": "Offline BusyBox HTTP service; local files only"},
        {"id": "task-worker", "description": "Offline BusyBox task worker; staged files only"},
    ], "scope": "locally_cached_stage_templates_only"}


def list_projects():
    with guarded():
        entries = _registry()
        return {"scope": "stage_compose_only",
                "projects": [_inspect(name, entry) for name, entry in sorted(entries.items())],
                "production_mutation_allowed": False}


def action(op, project=None, template=None):
    if op not in ("install", "start", "stop", "restart", "uninstall"):
        raise AppError("unsupported_compose_action", 400)
    with guarded():
        entries = _registry()
        stage_owner = registry()["owner"]
        if op == "install":
            if template not in TEMPLATES or project is not None:
                raise AppError("unsupported_staging_template", 400)
            if len(entries) >= LIMIT:
                raise AppError("stage_compose_capacity_reached", 409)
            project = "osd-m1-compose-" + secrets.token_hex(6)
            root = _project_dir(project)
            root.mkdir(mode=0o700)
            data = root / "data"
            data.mkdir(mode=0o700)
            # File durability test: read-only mount visible within app.
            (data / "index.html").write_text("OpenServerDesk isolated Compose application\n")
            config = root / "compose.yaml"
            config.write_text(_compose_content(project, stage_owner, template, data))
            try:
                _command("docker", "compose", "--project-name", project,
                         "--file", str(config), "up", "--detach",
                         "--no-build", "--pull", "never", timeout=70)
                names = _command("docker", "ps", "--all", "--quiet", "--no-trunc",
                                 "--filter", "label=com.docker.compose.project="+project)
                ids = names.splitlines()
                if len(ids) != 1 or not re.fullmatch("[a-f0-9]{64}", ids[0]):
                    raise AppError("unexpected_stage_compose_container_count", 503)
                entry = {"id": ids[0], "template": template, "owner": stage_owner}
                result = _inspect(project, entry)
                entries[project] = entry
                _save(entries)
                return {"operation": "installed", "app": result}
            except Exception:
                # Never run compose down: could remove unexpected objects.
                # Inspect the exact stage-owned container identity first;
                # if unknown, preserve it for investigation.
                if "entry" in locals():
                    try:
                        _inspect(project, entry)
                    except AppError:
                        pass
                    else:
                        _command("docker", "rm", "--force", entry["id"])
                raise
        if not isinstance(project, str) or project not in entries or template is not None:
            raise AppError("unknown_stage_compose_project", 404)
        entry = entries[project]
        previous = _inspect(project, entry)
        if op == "start" and previous["running"]:
            raise AppError("stage_compose_already_running", 409)
        if op == "stop" and not previous["running"]:
            raise AppError("stage_compose_already_stopped", 409)
        if op == "restart" and not previous["running"]:
            raise AppError("stage_compose_not_running", 409)
        if op == "start":
            _command("docker", "start", entry["id"])
        elif op == "stop":
            _command("docker", "stop", "--time", "2", entry["id"])
        elif op == "restart":
            _command("docker", "restart", "--time", "2", entry["id"])
        else:
            _command("docker", "rm", "--force", entry["id"])
            entries.pop(project)
            _save(entries)
            # Intentionally RETAIN stage-local application files as recovery
            # data; never delete a user volume or a production path.
            return {"operation": "uninstalled", "project": project,
                    "stage_data_retained": True, "production_mutation_allowed": False}
        return {"operation": op, "app": _inspect(project, entry)}
