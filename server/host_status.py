"""Read-only CasaOS replacement host status; never inspects user upload HDD."""
from __future__ import annotations
import os
from pathlib import Path

SSD = Path("/mnt/ssd-turbo")
PROC_MEM = Path("/proc/meminfo")
PROC_UPTIME = Path("/proc/uptime")


class HostStatusError(RuntimeError):
    pass


def _disk(path: Path):
    if path not in (Path("/"), SSD):
        raise HostStatusError("unapproved storage path")
    if path == SSD and (path.is_symlink() or not path.is_mount()):
        raise HostStatusError("trusted SSD mount absent")
    try:
        stat = os.statvfs(path)
    except OSError:
        raise HostStatusError("host disk status unavailable")
    block = stat.f_frsize
    size = stat.f_blocks * block
    free = stat.f_bavail * block
    if size <= 0 or free < 0 or free > size:
        raise HostStatusError("invalid disk capacity")
    return {
        "total_bytes": size,
        "free_bytes": free,
        "used_percent": round(100 * (size-free) / size, 1),
    }


def _mem():
    try:
        lines = PROC_MEM.read_text().splitlines()
        values = {}
        for line in lines:
            key, _, raw = line.partition(":")
            if key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                values[key] = int(raw.strip().split()[0]) * 1024
        if not 0 < values["MemAvailable"] <= values["MemTotal"]:
            raise HostStatusError("invalid system memory")
        if values["SwapFree"] > values["SwapTotal"]:
            raise HostStatusError("invalid system swap")
        return {
            "total_bytes": values["MemTotal"],
            "available_bytes": values["MemAvailable"],
            "used_percent": round(
                100 * (values["MemTotal"] - values["MemAvailable"]) / values["MemTotal"], 1),
            "swap_total_bytes": values["SwapTotal"],
            "swap_free_bytes": values["SwapFree"],
        }
    except (OSError, ValueError, KeyError, IndexError):
        raise HostStatusError("host memory status unavailable")


def status():
    try:
        uptime = float(PROC_UPTIME.read_text().split()[0])
        loads = os.getloadavg()
        cores = os.cpu_count()
        if (uptime <= 0 or cores is None or cores < 1
                or len(loads) != 3 or any(v < 0 or v > 100000 for v in loads)):
            raise HostStatusError("invalid host metrics")
        return {
            "source": "local_linux_readonly",
            "scope": "nas_root_and_ssd_only",
            "uptime_seconds": round(uptime),
            "cpu_logical_cores": cores,
            "load_averages": [round(v, 2) for v in loads],
            "memory": _mem(),
            "filesystems": {
                "system": _disk(Path("/")),
                "ssd": _disk(SSD),
            },
            "external_user_data_disks_inspected": False,
            "production_modified": False,
            "migration_allowed": False,
        }
    except (OSError, ValueError, IndexError):
        raise HostStatusError("host status unavailable")


if __name__ == "__main__":
    import json
    print(json.dumps(status(), sort_keys=True))
