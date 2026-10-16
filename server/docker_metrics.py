"""Sanitized Docker container resource stats for a local-only NAS dashboard.

Read-only fixed Docker CLI. No inspect, exec, logs, mount path access,
environment variables, filesystem paths or user controlled arguments.
Only counters from docker stats are exposed, with IDs already appearing
in the separately approved Docker inventory. Fail closed on malformed data.
"""
from __future__ import annotations
import datetime as dt
import json
import math
import re
import subprocess

from docker_readonly import inventory, InventoryUnavailable

STATS_COMMAND = (
    "docker", "stats", "--all", "--no-stream", "--format", "{{json .}}",
)
PERCENT = re.compile(r"^(?:[0-9]+)(?:\.[0-9]{1,4})?%$")
SIZE = re.compile(
    r"^([0-9]+(?:\.[0-9]{1,4})?)(B|kB|MB|GB|TB|KiB|MiB|GiB|TiB)$"
)
SCALE = {
    "B": 1,
    "kB": 1000, "MB": 1000000, "GB": 1000000000,
    "TB": 1000000000000,
    "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3,
    "TiB": 1024**4,
}
PUBLIC_FIELDS = {"id","cpu_percent","memory_used_bytes",
                 "memory_limit_bytes","memory_percent","pids"}


class MetricsUnavailable(Exception):
    """Stats unavailable; do not substitute plausible-looking zeros."""


def _percentage(value):
    if not isinstance(value, str) or not PERCENT.fullmatch(value):
        raise MetricsUnavailable("invalid Docker percentage")
    parsed = float(value[:-1])
    if not math.isfinite(parsed) or parsed > 100000:
        raise MetricsUnavailable("unreasonable Docker percentage")
    return parsed


def _size(value):
    if not isinstance(value, str):
        raise MetricsUnavailable("invalid Docker size")
    match = SIZE.fullmatch(value)
    if not match:
        raise MetricsUnavailable("unknown Docker unit")
    number = float(match.group(1))
    if not math.isfinite(number) or number < 0:
        raise MetricsUnavailable("invalid Docker size")
    return int(number * SCALE[match.group(2)])


def _memory(value):
    if not isinstance(value, str):
        raise MetricsUnavailable("invalid memory pair")
    parts = value.split(" / ")
    if len(parts) != 2:
        raise MetricsUnavailable("invalid memory pair")
    return _size(parts[0]), _size(parts[1])


def _pid(value):
    if value in ("--","N/A"):
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,8}",value):
        raise MetricsUnavailable("invalid process count")
    return int(value)


def _run():
    try:
        output = subprocess.run(
            STATS_COMMAND, capture_output=True, text=True,
            timeout=25, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        raise MetricsUnavailable("Docker stats engine unreachable")
    if output.returncode != 0 or len(output.stdout) > 1000000:
        raise MetricsUnavailable("Docker stats unavailable")
    return output.stdout


def metrics():
    observed = inventory()
    allowed = {entry["id"] for entry in observed["containers"]}
    if len(allowed) != observed["container_count"]:
        raise MetricsUnavailable("ambiguous Docker inventory identities")
    text = _run()
    lines = text.splitlines()
    if len(lines) > 10000:
        raise MetricsUnavailable("excessive Docker resource rows")
    entries = []
    seen = set()
    for line in lines:
        try:
            raw = json.loads(line)
        except ValueError:
            raise MetricsUnavailable("malformed Docker stats JSON")
        if not isinstance(raw, dict):
            raise MetricsUnavailable("invalid Docker row")
        ident = raw.get("ID")
        if (not isinstance(ident, str)
                or not re.fullmatch("[0-9a-f]{12}", ident)
                or ident not in allowed or ident in seen):
            raise MetricsUnavailable("unrecognized Docker stats identity")
        seen.add(ident)
        used, limit = _memory(raw.get("MemUsage"))
        mem_pct = _percentage(raw.get("MemPerc"))
        if mem_pct > 100.0:
            raise MetricsUnavailable("unreasonable memory usage")
        entries.append({
            "id":ident,
            "cpu_percent":_percentage(raw.get("CPUPerc")),
            "memory_used_bytes":used,
            "memory_limit_bytes":limit,
            "memory_percent":mem_pct,
            "pids":_pid(raw.get("PIDs")),
        })
    if seen != allowed:
        # Docker can be changing while we read it. Avoid pretending stale
        # partial stats are complete instead of returning an error.
        raise MetricsUnavailable("Docker stats race: container set changed")
    return {
        "source":"local_docker_resource_metrics_readonly",
        "observed_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        "container_count":len(entries),
        "containers":sorted(entries,key=lambda row:row["id"]),
        "production_modified":False,
        "external_user_data_inspected":False,
        "migration_allowed":False,
    }
