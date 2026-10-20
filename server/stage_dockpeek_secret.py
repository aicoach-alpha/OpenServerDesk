"""Random, stage-project-local Dockpeek SECRET_KEY. Never use CasaOS secrets.

Only the exact curated Dockpeek image may receive this one environment key.
It is stable across start/stop, update, rollback and data checkpoint.
"""
from __future__ import annotations
import json
import os
import re
import secrets
import stat
from pathlib import Path

from stage_apps import AppError
from stage_host_socket import DOCKPEEK_ID,DOCKPEEK_SERVICE

ROOT=Path("/opt/openserverdesk-dev/runtime-stage/stage-app-manager/store-compiled")
PROJECT=re.compile(r"osd-compiled-[0-9a-f]{12}\Z")
KEY=re.compile(r"[0-9a-f]{64}\Z")
FILENAME="dockpeek-staging-secret.json"


def _path(project):
    if not isinstance(project,str) or not PROJECT.fullmatch(project):
        raise AppError("invalid_dockpeek_secret_project",400)
    return ROOT/project/FILENAME


def create(project):
    path=_path(project)
    parent=path.parent
    if (path.is_symlink() or path.exists() or parent.is_symlink()
        or not parent.is_dir() or parent.stat().st_uid!=1000
        or parent.stat().st_mode & 0o077
        or parent.stat().st_dev!=ROOT.stat().st_dev):
        raise AppError("unsafe_dockpeek_secret_destination",403)
    payload=json.dumps({"version":1,"secret_key":secrets.token_hex(32)})
    flags=os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW
    fd=os.open(path,flags,0o600)
    try:
        with os.fdopen(fd,"w") as handle:
            handle.write(payload+"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path,0o600)
        dirfd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(dirfd)
        finally:os.close(dirfd)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def credential(project):
    path=_path(project)
    try:info=path.lstat()
    except OSError:raise AppError("dockpeek_stage_secret_missing",503)
    if (not stat.S_ISREG(info.st_mode) or
        stat.S_IMODE(info.st_mode)!=0o600 or info.st_uid!=1000 or
        info.st_dev!=ROOT.stat().st_dev or not 20<info.st_size<=160):
        raise AppError("unsafe_dockpeek_stage_secret",403)
    try:data=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError):raise AppError("invalid_dockpeek_stage_secret",503)
    if (not isinstance(data,dict) or set(data)!={"version","secret_key"} or
        data["version"]!=1 or not isinstance(data["secret_key"],str) or
        not KEY.fullmatch(data["secret_key"])):
        raise AppError("invalid_dockpeek_stage_secret",503)
    return data["secret_key"]


def environment(project):
    # Dockpeek's own login would require a second password-distribution
    # workflow. This pilot is reachable only behind the authenticated
    # OpenServerDesk staging gateway; do not expose it as a public service.
    return {"SECRET_KEY":credential(project),"DISABLE_AUTH":"true"}


def allow_configuration(project,services):
    if not isinstance(services,dict) or set(services)!={DOCKPEEK_SERVICE}:
        return False
    cfg=services[DOCKPEEK_SERVICE]
    if cfg.get("labels",{}).get("osd.m1.compiled.app")!=DOCKPEEK_ID:
        return False
    return (cfg.get("environment")==environment(project) and
            cfg.get("healthcheck") is None)
