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
GLANCES_ID="github.com:com.bigbeartechworld.glances"
GLANCES_SERVICE="big-bear-glances"
GLANCES_IMAGE=("nicolargo/glances:4.5.3.2-full@sha256:"
    "2d16ab0fdba4b9f61b327f78dbb8a7e7931f4967be8e1db4d37326e4680e8433")
GLANCES_ENV={"GLANCES_OPT":"-w","USER":"stageglances","LOGNAME":"stageglances"}
WUD_ID="github.com:com.bigbeartechworld.whats-up-docker"
WUD_SERVICE="app"
WUD_IMAGE=("fmartinou/whats-up-docker:6.6.1@sha256:"
    "7cbdfa9bb56de7ad820e3efea16205c3cf09e5f06192436530c5c798964607f0")

APPROVED_PILOTS={
    PILOT_ID:(PILOT_SERVICE,PILOT_IMAGE),
    DOCKPEEK_ID:(DOCKPEEK_SERVICE,DOCKPEEK_IMAGE),
    GLANCES_ID:(GLANCES_SERVICE,GLANCES_IMAGE),
    WUD_ID:(WUD_SERVICE,WUD_IMAGE),
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
    if app_id==GLANCES_ID and (
            not isinstance(cfg.get("environment"),list)
            or len(cfg["environment"])!=2
            or set(cfg["environment"])!={"GLANCES_OPT=-w","TZ=UTC"}
            or cfg.get("ports")!=["61208:61208"]
            or cfg.get("pid")!="host"):
        return False
    if app_id==WUD_ID and (
            cfg.get("environment") not in (None,{})
            or cfg.get("ports")!=["3000:3000"]
            or cfg.get("depends_on")):
        return False
    # Refuse any privilege, host namespaces, additional device mounts or
    # custom entrypoints; these pilots need just the facade read endpoint.
    if any(cfg.get(field) for field in (
            "privileged","devices","cap_add","ipc","network_mode",
            "security_opt","entrypoint","command")):
        return False
    # The Glances source metadata requests host PID, but the generated stage
    # manifest must discard it. Never allow a privileged PID namespace.
    if cfg.get("pid") and app_id!=GLANCES_ID:
        return False
    vols=cfg.get("volumes")
    return isinstance(vols,list) and len(vols)==1 and _socket_item(vols[0])


def approved_service(app_id):
    item=APPROVED_PILOTS.get(app_id)
    return item[0] if item else None


def approved_app(app_id):
    return app_id in APPROVED_PILOTS


def glances_environment():
    # Deliberately discard all original host-specific environment options.
    # Glances is web-enabled only and monitors its stage container, NOT the
    # host, until a separately reviewed host metric adapter exists.
    return dict(GLANCES_ENV)


def allow_glances_environment(project,services):
    if not isinstance(services,dict) or set(services)!={GLANCES_SERVICE}:
        return False
    cfg=services[GLANCES_SERVICE]
    return (
        cfg.get("labels",{}).get("osd.m1.compiled.app")==GLANCES_ID
        and cfg.get("environment")==GLANCES_ENV
        and cfg.get("healthcheck") is None
    )


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
