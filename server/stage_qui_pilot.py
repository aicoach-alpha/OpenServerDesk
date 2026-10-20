"""Exact CasaOS Qui+PostgreSQL staging pilot. No production secrets."""
from __future__ import annotations
import json
import os
import re
import secrets
from pathlib import Path
from stage_apps import AppError
from stage_store_general import _find_catalog_definition

ROOT=Path("/opt/openserverdesk-dev/runtime-stage/stage-app-manager/store-compiled")
APP="casaos.app:org.icewhale.qui"
IMAGES={"qui":"ghcr.io/autobrr/qui:v1.28.0","postgres":"postgres:16-alpine"}
PROJECT=re.compile(r"osd-compiled-[0-9a-f]{12}\Z")
CREDENTIAL=re.compile(r"[0-9a-f]{48}\Z")
HEALTH={"test":["CMD-SHELL","pg_isready -U osdqui -d osdqui"],
        "interval":"5s","timeout":"3s","retries":12,"start_period":"10s"}

def supported(app_id,doc):
    if app_id!=APP or not isinstance(doc,dict) or set(doc.get("services",{}))!=set(IMAGES):
        return False
    a,b=doc["services"]["qui"],doc["services"]["postgres"]
    return (a.get("image")==IMAGES["qui"] and b.get("image")==IMAGES["postgres"]
            and a.get("depends_on")=={"postgres":{"condition":"service_healthy"}}
            and sorted(a.get("environment",{}))==["QUI__DATABASE_DSN","QUI__DATABASE_ENGINE"]
            and sorted(b.get("environment",{}))==["POSTGRES_DB","POSTGRES_PASSWORD","POSTGRES_USER"]
            and not a.get("privileged") and not b.get("privileged")
            and not a.get("network_mode") and not b.get("network_mode"))

def _path(project):
    if not isinstance(project,str) or not PROJECT.fullmatch(project):
        raise AppError("invalid_qui_staging_project",400)
    return ROOT/project/"qui-staging-secret.json"

def create(project):
    """Only runtime install calls this before the compiler; root-only on stage SSD."""
    path=_path(project)
    if path.exists() or path.is_symlink():
        raise AppError("qui_stage_secret_already_exists",409)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise AppError("unsafe_qui_stage_secret_directory",403)
    payload=json.dumps({"version":1,"password":secrets.token_hex(24)})
    flags=os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW
    fd=os.open(path,flags,0o600)
    try:
        with os.fdopen(fd,"w") as file:
            file.write(payload+"\n");file.flush();os.fsync(file.fileno())
        path.chmod(0o600)
        dr=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(dr)
        finally:os.close(dr)
    except Exception:
        path.unlink(missing_ok=True)
        raise

def credential(project):
    path=_path(project)
    if path.is_symlink() or not path.is_file():
        raise AppError("qui_stage_secret_missing",503)
    stat=path.stat()
    if (stat.st_mode&0o077 or stat.st_uid!=0 or stat.st_size>160
            or stat.st_dev!=ROOT.stat().st_dev):
        raise AppError("qui_stage_secret_unsafe",403)
    try:row=json.loads(path.read_text())
    except PermissionError as err:
        # Preserve the root-only credential; a read-only staging listing
        # may report this project as restricted instead of exposing it.
        raise AppError("qui_stage_secret_access_denied",503) from err
    except (OSError,ValueError):
        raise AppError("qui_stage_secret_corrupt",503)
    if (not isinstance(row,dict) or set(row)!={"version","password"}
            or row["version"]!=1 or not isinstance(row["password"],str)
            or not CREDENTIAL.fullmatch(row["password"])):
        raise AppError("qui_stage_secret_invalid",503)
    return row["password"]

def environments(project):
    pw=credential(project)
    return {
      "postgres":{"POSTGRES_DB":"osdqui","POSTGRES_USER":"osdqui",
                  "POSTGRES_PASSWORD":pw},
      "qui":{"QUI__DATABASE_ENGINE":"postgres",
             "QUI__DATABASE_DSN":
              "postgres://osdqui:"+pw+"@postgres:5432/osdqui?sslmode=disable"},
    }

def allow_configuration(project,services):
    """Any other app's environment and healthcheck remain forbidden."""
    if set(services)!=set(IMAGES):
        return False
    if any((services[k].get("labels") or {}).get("osd.m1.compiled.app")!=APP
           for k in IMAGES):
        return False
    expected=environments(project)
    return (all(services[k].get("environment")==expected[k] for k in IMAGES)
            and services["postgres"].get("healthcheck")==HEALTH
            and not services["qui"].get("healthcheck"))


def allow_configuration_readonly(project, services):
    """Validate Qui's manifest for read-only status without opening root secret.

    The Docker owner's immutable labels, full IDs, networks, mounts and the
    actual container environments are separately checked by stage_store_runtime.
    This does NOT authenticate the saved password against the root-only file.
    """
    path = _path(project)
    try:
        metadata = path.lstat()
    except OSError:
        return False
    import stat
    if (not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0 or metadata.st_gid != 0
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or not 1 <= metadata.st_size <= 160
            or metadata.st_dev != ROOT.stat().st_dev):
        return False
    if set(services) != set(IMAGES):
        return False
    if any((services[name].get("labels") or {}).get("osd.m1.compiled.app") != APP
           for name in IMAGES):
        return False
    pg = services["postgres"]
    qui = services["qui"]
    pg_env = pg.get("environment")
    qui_env = qui.get("environment")
    if not isinstance(pg_env, dict) or not isinstance(qui_env, dict):
        return False
    if (set(pg_env) != {"POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"}
            or set(qui_env) != {"QUI__DATABASE_ENGINE", "QUI__DATABASE_DSN"}):
        return False
    password = pg_env["POSTGRES_PASSWORD"]
    if not isinstance(password, str) or not CREDENTIAL.fullmatch(password):
        return False
    return (
        pg_env["POSTGRES_DB"] == "osdqui"
        and pg_env["POSTGRES_USER"] == "osdqui"
        and qui_env["QUI__DATABASE_ENGINE"] == "postgres"
        and qui_env["QUI__DATABASE_DSN"] ==
          "postgres://osdqui:" + password + "@postgres:5432/osdqui?sslmode=disable"
        and pg.get("healthcheck") == HEALTH
        and not qui.get("healthcheck")
        and qui.get("depends_on") ==
          {"postgres": {"condition": "service_healthy"}}
    )
