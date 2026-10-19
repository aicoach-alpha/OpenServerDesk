"""Offline, read-only PostgreSQL integrity evidence for the exact Qui pilot.

Never execute the original CasaOS Compose, never touch production volumes.
"""
from __future__ import annotations
import re
import subprocess
from pathlib import Path
from stage_apps import AppError
from stage_qui_pilot import APP

DIGEST=re.compile(r"sha256:[0-9a-f]{64}\Z")
STATUS=re.compile(r"^Database cluster state:\s+shut down\s*$",re.M)

def is_qui_pg(manifest):
    services=manifest.get("services",{})
    if set(services)!={"qui","postgres"}:
        return False
    return all((s.get("labels") or {}).get("osd.m1.compiled.app")==APP
               for s in services.values())

def verify(project,manifest,pgdata,stage_root):
    """Only a verified stage-owned PGDATA, no network and no writeable mounts."""
    if not is_qui_pg(manifest):
        return False
    root=Path(stage_root)/project
    pgdata=Path(pgdata)
    if not pgdata.is_relative_to(root) or pgdata.is_symlink() or not pgdata.is_dir():
        raise AppError("unsafe_stage_postgres_data_path",403)
    # Check each parent for symlinks or a filesystem escape.
    cur=pgdata
    while cur!=root:
        if cur.is_symlink() or cur.stat().st_dev!=root.stat().st_dev:
            raise AppError("unsafe_stage_postgres_data_path",403)
        cur=cur.parent
    if pgdata.name!="volume-0" or pgdata.parent.name!="postgres":
        raise AppError("unsafe_stage_postgres_data_path",403)
    version=pgdata/"PG_VERSION"
    control=pgdata/"global"/"pg_control"
    if (version.is_symlink() or not version.is_file() or version.stat().st_size>8
            or version.read_text().strip()!="16" or control.is_symlink()
            or not control.is_file() or control.stat().st_size!=8192
            or (pgdata/"postmaster.pid").exists()):
        raise AppError("stage_postgres_cold_data_invalid",409)
    # Cold snapshots are root-owned, restored stage files UID1000.
    # No-capabilities UID0 cannot bypass 0600 owner read permissions.
    stat_control=control.stat()
    if ((stat_control.st_uid,stat_control.st_gid) not in ((0,0),(1000,1000))
            or version.stat().st_uid!=stat_control.st_uid):
        raise AppError("stage_postgres_cold_owner_invalid",403)
    reader_uid=str(stat_control.st_uid)+":"+str(stat_control.st_gid)
    source=manifest["services"]["postgres"]
    image=source.get("image")
    if not isinstance(image,str) or not DIGEST.fullmatch(image):
        raise AppError("unsafe_stage_postgres_image",403)
    # Match the verified pg_control owner in the no-network, read-only
    # cap-drop-all inspection container, with no writeable mounts.
    cmd=("docker","run","--rm","--network","none","--read-only",
         "--pull","never","--user",reader_uid,
         "--cap-drop","ALL","--security-opt","no-new-privileges",
         "--pids-limit","24","--memory","128m",
         "--mount","type=bind,src="+str(pgdata)+",dst=/pgdata,readonly",
         "--entrypoint","pg_controldata",image,"/pgdata")
    try:
        result=subprocess.run(cmd,capture_output=True,text=True,
                              timeout=17,check=False)
    except (OSError,subprocess.TimeoutExpired) as err:
        raise AppError("stage_postgres_cold_check_unavailable",503) from err
    if (result.returncode or len(result.stdout)>10000
            or not STATUS.search(result.stdout)
            or "Database system identifier:" not in result.stdout):
        raise AppError("stage_postgres_cold_integrity_failed",409)
    return True
