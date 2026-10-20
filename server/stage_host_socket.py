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
    if app_id!=PILOT_ID or not isinstance(doc,dict):
        return False
    services=doc.get("services")
    if (not isinstance(services,dict) or set(services)!={PILOT_SERVICE}
            or not isinstance(services[PILOT_SERVICE],dict)):
        return False
    cfg=services[PILOT_SERVICE]
    if cfg.get("image")!=PILOT_IMAGE:
        return False
    vols=cfg.get("volumes")
    return isinstance(vols,list) and len(vols)==1 and _socket_item(vols[0])


def adapted_service(app_id,doc,name,service):
    if not eligible(app_id,doc) or name!=PILOT_SERVICE:
        raise AppError("host_socket_pilot_not_approved",403)
    return {**service,"volumes":[]}


def socket_mount():
    return {
        "type":"bind","source":str(SOCKET_PATH),"target":TARGET,
        "bind":{"create_host_path":False},"read_only":True,
    }


def is_facade_mount(item):
    return isinstance(item,dict) and item==socket_mount()
