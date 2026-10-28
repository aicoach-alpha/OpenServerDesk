#!/usr/bin/env python3
"""Config-only recovery-media preflight; never includes external Nextcloud data.

Never reads application contents, copies data or mutates Docker. The source
list comes solely from fresh Docker inspection, never from an HTTP caller.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path

from m1_cold_backup import _paths_fresh

STAGING = Path("/home/andre/projects/openserverdesk/operations/runtime-stage")
# Deliberately NEVER inspect /mnt/data or other external user data mounts.
LOCAL_MOUNTS = (Path("/"), Path("/mnt/ssd-turbo"))


def inspect(target: Path | None = None):
    report, sources = _paths_fresh()
    source_fs = {os.stat(path).st_dev for path in sources}
    existing = [p for p in LOCAL_MOUNTS if p.is_dir()]
    candidates = [{
        "kind": "staging_root" if path == STAGING else (
            "system_root" if path == Path("/") else "other_local_mount"),
        "independent": path.stat().st_dev not in source_fs,
        "free_gib": round(os.statvfs(path).f_bavail * os.statvfs(path).f_frsize / 1024**3, 2),
    } for path in existing]
    if target is not None:
        t = Path(target)
        if (not t.is_absolute() or ".." in t.parts or t.is_symlink()
                or not t.is_dir() or not t.is_mount()):
            raise ValueError("backup target must be an existing trusted filesystem mount root")
        independent = t.stat().st_dev not in source_fs
        free = os.statvfs(t).f_bavail * os.statvfs(t).f_frsize
        target_report = {
            "supplied": True, "different_device_from_every_source": independent,
            "free_gib": round(free / 1024**3, 2),
            "capacity_sized_for_full_restore": False,
        }
    else:
        target_report = {
            "supplied": False, "different_device_from_every_source": False,
            "capacity_sized_for_full_restore": False,
        }
    return {
        "assessment": "CASAOS_CONFIG_ONLY_DEVICE_ISOLATION_READ_ONLY",
        "external_user_data_copied": False,
        "external_user_data_inspected": False,
        "selected_platform_config_source_count": len(sources),
        "source_count": len(sources),
        "source_filesystem_count": len(source_fs),
        "running_containers": report["running_container_count"],
        "local_mount_choices": candidates,
        "independent_target": target_report,
        "production_modified": False,
        # Full sizing and restore proof are separate safety requirements.
        "migration_allowed": False,
        "status": "blocked_until_platform_config_recovery_verified",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.target), sort_keys=True))
