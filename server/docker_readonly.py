"""Strictly read-only Docker inventory over the local Engine Unix socket.

No caller-controlled Docker API paths, no write methods, no raw Docker
inspect/config/labels/environment, and no HTTP access outside loopback.
"""
import http.client
import json
import os
import socket
import stat
from pathlib import Path

SOCKET = Path("/var/run/docker.sock")
STAGING_OPT_IN = Path("/home/andre/projects/openserverdesk/operations/runtime-stage/.enable-docker-inventory")
STAGING_OPT_IN_CONTENT = "OSD_STAGING_DOCKER_INVENTORY_V1\n"

def _inventory_opted_in():
    if os.environ.get("OSD_DOCKER_READ_ONLY") == "1":
        return True
    # Operator-owned stage marker, not a service-unit change. Reject symlink,
    # group/world writable marker and unexpected contents (fail closed).
    try:
        meta = STAGING_OPT_IN.lstat()
        if not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0 or meta.st_mode & 0o022:
            return False
        return STAGING_OPT_IN.read_text() == STAGING_OPT_IN_CONTENT
    except (OSError, UnicodeError):
        return False



class InventoryUnavailable(RuntimeError):
    pass


class UnixDockerConnection(http.client.HTTPConnection):
    def __init__(self, timeout=3):
        super().__init__("localhost", timeout=timeout)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(str(SOCKET))


def _read(path):
    if path not in ("/_ping", "/containers/json?all=1"):
        raise ValueError("unapproved Docker API route")
    conn = UnixDockerConnection()
    try:
        conn.request("GET", path, headers={"Host": "docker", "Accept": "application/json"})
        response = conn.getresponse()
        data = response.read(4_000_001)
        if len(data) > 4_000_000:
            raise InventoryUnavailable("Docker response too large")
        if response.status != 200:
            raise InventoryUnavailable("Docker inventory unavailable")
        return data
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise InventoryUnavailable("Docker socket read failed") from exc
    finally:
        conn.close()


def inventory():
    if not _inventory_opted_in():
        raise InventoryUnavailable("Docker inventory is disabled")
    raw = json.loads(_read("/containers/json?all=1"))
    if not isinstance(raw, list) or len(raw) > 10000:
        raise InventoryUnavailable("unexpected Docker inventory")
    containers = []
    for item in raw:
        if not isinstance(item, dict):
            raise InventoryUnavailable("invalid Docker container entry")
        labels = item.get("Labels") or {}
        if not isinstance(labels, dict):
            labels = {}
        names = item.get("Names") or []
        if not isinstance(names, list):
            names = []
        state = item.get("State", "unknown")
        if state not in ("running", "exited", "created", "paused", "restarting", "dead", "removing"):
            state = "unknown"
        ports = []
        for port in item.get("Ports") or []:
            if not isinstance(port, dict):
                continue
            exposed = {"private": port.get("PrivatePort"),
                       "protocol": str(port.get("Type", "tcp"))[:8]}
            if isinstance(port.get("PublicPort"), int):
                exposed["public"] = port["PublicPort"]
            ports.append(exposed)
        containers.append({
            "id": str(item.get("Id", ""))[:12],
            "name": str(names[0]).lstrip("/")[:160] if names else "",
            "image": str(item.get("Image", ""))[:220],
            "state": state,
            "status": str(item.get("Status", ""))[:120],
            "compose_project": str(labels.get("com.docker.compose.project", ""))[:100],
            "ports": ports[:50],
        })
    containers.sort(key=lambda item: item["name"])
    counts = {}
    projects = {}
    for item in containers:
        counts[item["state"]] = counts.get(item["state"], 0) + 1
        if item["compose_project"]:
            projects[item["compose_project"]] = projects.get(item["compose_project"], 0) + 1
    return {
        "source": "local_docker_engine_read_only",
        "container_count": len(containers),
        "states": counts,
        "compose_projects": [{"name": k, "containers": v} for k, v in sorted(projects.items())],
        "containers": containers,
    }
