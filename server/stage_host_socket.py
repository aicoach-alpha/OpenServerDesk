"""Explicit single-app staging Docker API facade mount contract.

Strict equality with an immutable approved CasaOS catalog definition. Never
read from, mount or connect to the actual host Docker Unix socket.
"""
from pathlib import Path
from stage_apps import AppError

PILOT_ID="github.com:com.bigbeartechworld.dozzle"
PILOT_SERVICE="app"
PILOT_IMAGE=("amir20/dozzle:v11.1.1@sha256:"
    "c90494cbc3a9ca959634b89fdb3fdecbcbae1f690d7a567d0d356c6fda1d957c")
# Fixed, digest-pinned catalogue-only allowlist. Adding a repository here
# never authorizes production Docker access: every app receives the SAME
# synthetic staging metadata socket and read-only runtime restrictions.
DOCKPEEK_ID="github.com:com.bigbeartechworld.dockpeek"
DOCKPEEK_SERVICE="big-bear-dockpeek"
DOCKPEEK_IMAGE=("ghcr.io/dockpeek/dockpeek:v1.7.2@sha256:"
    "87654d0104eacff48a70c7c1eea6126f19f5803b21bfdace842ae765351593b4")
APPROVED_PILOTS={
    PILOT_ID:(PILOT_SERVICE,PILOT_IMAGE),
    DOCKPEEK_ID:(DOCKPEEK_SERVICE,DOCKPEEK_IMAGE),
}
LABEL="osd.m1.compiled.broker"
LABEL_VALUE="stage-docker-readonly-v1"
SOCKET_ROOT=Path("/opt/openserverdesk-dev/runtime-stage/stage-app-manager/host-broker")
SOCKET_PATH=SOCKET_ROOT/"dozzle-stage-readonly.sock"
TARGET="/var/run/docker.sock"
ADAPTER="docker_stage_metadata_readonly_v1"


def _socket_item(item):
    if isinstance(item,str):
        parts=item.split(":")
        return (len(parts) in (2,3) and parts[1]==TARGET and
                (len(parts)==2 or parts[2]=="ro"))
    if isinstance(item,dict):
        return (item.get("type") in ("bind","volume") and
                item.get("target")==TARGET and
                item.get("read_only") is not False)
    return False


def eligible(app_id,doc):
    permitted=APPROVED_PILOTS.get(app_id)
    if permitted is None or not isinstance(doc,dict):
        return False
    expected_service,expected_image=permitted
    services=doc.get("services")
    if (not isinstance(services,dict) or set(services)!={expected_service}
            or not isinstance(services[expected_service],dict)):
        return False
    cfg=services[expected_service]
    if cfg.get("image")!=expected_image:
        return False
    # Refuse any privilege, host namespaces, additional device mounts or
    # custom entrypoints; these pilots need just the facade read endpoint.
    if any(cfg.get(field) for field in (
            "privileged","devices","cap_add","pid","ipc","network_mode",
            "security_opt","entrypoint","command")):
        return False
    vols=cfg.get("volumes")
    return isinstance(vols,list) and len(vols)==1 and _socket_item(vols[0])


def approved_service(app_id):
    item=APPROVED_PILOTS.get(app_id)
    return item[0] if item else None


def approved_app(app_id):
    return app_id in APPROVED_PILOTS


def adapted_service(app_id,doc,name,service):
    if not eligible(app_id,doc) or name!=approved_service(app_id):
        raise AppError("host_socket_pilot_not_approved",403)
    return {**service,"volumes":[]}


def socket_mount():
    return {
        "type":"bind","source":str(SOCKET_PATH),"target":TARGET,
        "bind":{"create_host_path":False},"read_only":True,
    }


def is_facade_mount(item):
    return isinstance(item,dict) and item==socket_mount()
