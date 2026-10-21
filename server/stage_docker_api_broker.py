"""Docker API *compatibility facade* for explicitly approved staging apps.

This is NOT a Docker socket proxy. It never forwards bytes to the real Docker
daemon, offers no host Docker API, and returns only records obtained after the
OpenServerDesk staging registry and container provenance checks. By default
all Docker-like endpoints except the few safe GET paths are denied.
"""
from __future__ import annotations

import json
import datetime
import selectors
import struct
import subprocess
import time
import os
import re
import socket
import socketserver
import stat
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit,parse_qsl

from stage_apps import AppError
from stage_host_socket import SOCKET_ROOT, SOCKET_PATH, APPROVED_PILOTS
from stage_store_compiler import resolve_image, EGRESS_PILOT_ID, EGRESS_PILOT_IMAGE
from stage_docker_api_stats import cached_snapshot as stage_stats_snapshot
CID=re.compile(r"[a-f0-9]{64}\Z")
CID_REF=re.compile(r"[a-f0-9]{12,64}\Z")
IMAGE_DIGEST=re.compile(r"sha256:[a-f0-9]{64}\Z")
IMAGE_REF=re.compile(r"(?:sha256:)?[a-f0-9]{64}\Z")
CATALOG_TAG=re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,180}:[A-Za-z0-9_.-]{1,90}\Z")
# This is a *fixed*, audited subset of stage app identities. A tag is never
# read from an untrusted container label or arbitrary host Docker images.
PINNED_SOURCE_IMAGES={
    (app_id,service):image
    for app_id,(service,image) in APPROVED_PILOTS.items()
}
PINNED_SOURCE_IMAGES[(EGRESS_PILOT_ID,"myspeed")]=EGRESS_PILOT_IMAGE
PINNED_CATALOG_ALIASES=frozenset(
    ref.split("@sha256:",1)[0] for ref in PINNED_SOURCE_IMAGES.values()
)
PROJECT=re.compile(r"osd-compiled-[a-f0-9]{12}\Z")
PREFIX=re.compile(r"/v[0-9]{1,2}\.[0-9]{1,2}(?=/|$)")
MAX_CONTAINERS=16
_CACHE_LOCK=threading.Lock()
_CACHE_ROWS=()
_CACHE_EXPIRES=0.0
STAGE_INVENTORY_TTL=3.0
MAX_LOG_BYTES=64*1024
MAX_LOG_TAIL=160
MAX_LOG_SECONDS=5.5
_LOG_SLOTS=threading.BoundedSemaphore(2)
_EVENT_SLOTS=threading.BoundedSemaphore(2)
_STATS_SLOTS=threading.BoundedSemaphore(4)
MAX_EVENT_SECONDS=600.0
MAX_STATS_SECONDS=180.0
EVENT_HEARTBEAT_SECONDS=9.0


def _verified_catalog_tag(app_id,service,image_id,*,resolver=resolve_image):
    """Display-only alias for an exact trusted catalog source that resolves
    locally to the already-verified immutable stage image ID.

    When a tag has been retargeted or a stage image has been version-switched,
    return no alias rather than misrepresent the installed image version.
    Never call a host-wide Docker image list.
    """
    if not isinstance(image_id,str) or not IMAGE_DIGEST.fullmatch(image_id):
        return None
    source=PINNED_SOURCE_IMAGES.get((app_id,service))
    if not source:
        return None
    alias=source.split("@sha256:",1)[0]
    if not CATALOG_TAG.fullmatch(alias):
        return None
    try:
        resolved=resolver(source)
    except (AppError,OSError,ValueError):
        return None
    return alias if resolved==image_id else None


def _refresh_stage_containers():
    # Lazy import avoids import cycles during stage compiler startup.
    from stage_store_runtime import _projects,_current,QUI_APP
    from stage_store_runtime import _folder
    result=[]
    registry=_projects()
    for project,entry in sorted(registry.items()):
        if not PROJECT.fullmatch(project):
            raise AppError("stage_broker_invalid_project",503)
        # Protected Qui, interrupted transitions and unknown owners are never
        # downgraded to unauthenticated broker metadata.
        if entry.get("app_id")==QUI_APP:
            continue
        pending=_folder(project)/"pending.json"
        if pending.exists() or pending.is_symlink():
            raise AppError("stage_broker_operation_in_progress",503)
        manifest,services=_current(project,entry)
        for name,item in sorted(services.items()):
            ident=item.get("id")
            spec=manifest.get("services",{}).get(name)
            image_id=spec.get("image") if isinstance(spec,dict) else None
            if (not isinstance(ident,str) or not CID.fullmatch(ident)
                or not isinstance(image_id,str)
                or not IMAGE_DIGEST.fullmatch(image_id)):
                raise AppError("stage_broker_invalid_container_or_image",503)
            # _current has already verified this immutable image against
            # the exact stage-owned container Config.Image and labels.
            # Resolve only a fixed, trusted catalog image reference to prove
            # the display tag still points to these exact image bytes.
            if spec["labels"].get("osd.m1.compiled.app")!=entry["app_id"]:
                raise AppError("stage_broker_catalog_identity_mismatch",403)
            alias=_verified_catalog_tag(entry["app_id"],name,image_id)
            labels={"osd.stage.scope":"staging-only",
                    "osd.stage.project":project}
            if alias is not None:
                labels["osd.stage.catalog.image_tag"]=alias
            result.append({
                "Id":ident,
                "Names":["/osd-stage-"+project+"-"+name],
                "Image":image_id,
                "ImageID":image_id,
                "State":"running" if item["running"] else "exited",
                "Status":"Stage app (isolated)",
                "Labels":labels,
                "Ports":[],
                "Mounts":[],
                "NetworkSettings":{"Networks":{}},
            })
            if len(result)>MAX_CONTAINERS:
                raise AppError("stage_broker_container_limit",503)
    return result


def stage_containers(*,fresh=False):
    """Short-lived, provenance-verified stage inventory.

    A refresh is serialized, preventing ten parallel Docker inspect sequences
    from Dozzle events/stats/listing from overwhelming the NAS. Container IDs
    cannot be reused for unrelated production containers.
    """
    global _CACHE_ROWS,_CACHE_EXPIRES
    with _CACHE_LOCK:
        if not fresh and _CACHE_ROWS and time.monotonic()<_CACHE_EXPIRES:
            return list(_CACHE_ROWS)
        records=_refresh_stage_containers()
        _CACHE_ROWS=tuple(records)
        _CACHE_EXPIRES=time.monotonic()+STAGE_INVENTORY_TTL
        return list(records)


def stage_images(rows=None):
    """Synthesize *only* image IDs already proven by stage-owned containers.

    Only fixed, locally resolved catalog tag aliases are exposed, never a
    host-wide Docker image inventory, real image config, file paths, secrets,
    unverified registry names or caller-supplied URLs.
    """
    rows=stage_containers() if rows is None else rows
    images={}
    tags={}
    for row in rows:
        if not isinstance(row,dict) or (row.get("Labels") or {}).get(
                "osd.stage.scope")!="staging-only":
            raise AppError("stage_broker_unverified_image_source",403)
        image_id=row.get("ImageID")
        if (not isinstance(image_id,str) or not IMAGE_DIGEST.fullmatch(image_id)
            or row.get("Image")!=image_id):
            raise AppError("stage_broker_unverified_image_source",403)
        images[image_id]=images.get(image_id,0)+1
        alias=row["Labels"].get("osd.stage.catalog.image_tag")
        if alias is not None:
            if (not isinstance(alias,str) or not CATALOG_TAG.fullmatch(alias)
                or alias not in PINNED_CATALOG_ALIASES):
                raise AppError("stage_broker_invalid_catalog_alias",403)
            # The alias was resolved by _refresh_stage_containers against a
            # fixed audited catalog source and the verified container digest.
            tags.setdefault(image_id,set()).add(alias)
            if len(tags[image_id])>MAX_CONTAINERS:
                raise AppError("stage_broker_image_tag_limit",503)
        if len(images)>MAX_CONTAINERS:
            raise AppError("stage_broker_image_limit",503)
    output=[]
    for image_id,used in sorted(images.items()):
        names=sorted(tags.get(image_id,()))
        labels={"osd.stage.scope":"staging-only",
                "osd.stage.image_source":"verified_container_manifest",
                "osd.stage.uses":str(used)}
        if names:
            labels["osd.stage.catalog.alias_source"]="pinned_local_digest"
        output.append({
            "Id":image_id,"ParentId":"","RepoTags":names,"RepoDigests":[],
            "Labels":labels,
            # Unknown timestamps and sizes must never be fabricated.
            "Created":0,"Size":0,"SharedSize":0,"VirtualSize":0,
            "Containers":used,
        })
    return output


def _resolve_stage_image(reference, images=None):
    if not isinstance(reference,str) or not IMAGE_REF.fullmatch(reference):
        raise AppError("invalid_stage_image_reference",400)
    image_id=reference if reference.startswith("sha256:") else "sha256:"+reference
    available=stage_images() if images is None else images
    for item in available:
        if item["Id"]==image_id:
            return item
    raise AppError("stage_image_not_registered",404)


def _resolve_stage_item(reference, rows=None):
    # Docker clients commonly use the first 12 hex characters of an ID.
    # Resolve only against our ALREADY VERIFIED staging container set.
    if not isinstance(reference,str) or not CID_REF.fullmatch(reference):
        raise AppError("invalid_stage_container_reference",400)
    options=[row for row in (rows if rows is not None else stage_containers())
             if row["Id"].startswith(reference)]
    if not options:
        raise AppError("stage_container_not_registered",404)
    if len(options)!=1:
        raise AppError("ambiguous_stage_container_reference",409)
    return options[0]


def _safe_log_time(raw):
    """Docker logs timestamp: Unix seconds/nanoseconds or valid RFC3339Nano."""
    if raw in ("","0"):
        return None
    # Go's zero time commonly serializes to a negative Unix timestamp with
    # nine fractional digits; it means no lower/upper date boundary.
    if isinstance(raw,str) and re.fullmatch(r"-[0-9]{1,11}(?:\.[0-9]{1,9})?",raw):
        return None
    if not isinstance(raw,str) or len(raw)>42:
        raise AppError("invalid_stage_log_timestamp",400)
    if raw.isascii() and raw.isdecimal() and len(raw)<=20:
        value=int(raw)
        # Some Go clients provide epoch nanoseconds, but Docker CLI expects
        # Unix seconds; reduce by 10^9 without allowing CLI option injection.
        if len(raw)>=16:
            value=value//1_000_000_000
        if value>4_102_444_800:  # future beyond 2100 is not meaningful
            raise AppError("invalid_stage_log_timestamp",400)
        return str(value)
    fraction=re.fullmatch(r"([0-9]{1,11})\.([0-9]{1,9})",raw)
    if fraction:
        if int(fraction.group(1))>4_102_444_800:
            raise AppError("invalid_stage_log_timestamp",400)
        return (None if not int(fraction.group(1)) and
                not int(fraction.group(2)) else raw)
    iso=re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"(?:\.[0-9]{1,9})?(?:Z|[+-][0-9]{2}:[0-9]{2})?",raw)
    if iso is None:
        raise AppError("invalid_stage_log_timestamp",400)
    try:
        datetime.datetime.fromisoformat(raw.replace("Z","+00:00"))
    except ValueError:
        raise AppError("invalid_stage_log_timestamp",400)
    return raw


def _log_request(query):
    """Parse only Docker log options that cannot influence host resources."""
    if not isinstance(query,str) or len(query)>250:
        raise AppError("invalid_stage_log_query",400)
    try:
        items=parse_qsl(query,keep_blank_values=True,strict_parsing=True,
                        max_num_fields=9)
    except ValueError:
        raise AppError("invalid_stage_log_query",400)
    opts={}
    for key,value in items:
        if key in opts or key not in (
            "tail","stdout","stderr","timestamps","follow","since",
            "until","details"):
            raise AppError("unsupported_stage_log_query",400)
        opts[key]=value
    for key in ("stdout","stderr","timestamps","follow","details"):
        if key in opts and opts[key] not in ("true","false","1","0"):
            raise AppError("invalid_stage_log_boolean",400)
    if opts.get("details") in ("true","1"):
        raise AppError("stage_log_details_denied",403)
    if opts.get("stdout") in ("false","0") and opts.get("stderr") in ("false","0"):
        raise AppError("stage_log_streams_disabled",400)
    tail=opts.get("tail","80")
    if tail=="all":
        tail=str(MAX_LOG_TAIL)  # clamp common Docker API shorthand
    if not tail.isascii() or not tail.isdecimal() or len(tail)>3:
        raise AppError("invalid_stage_log_tail",400)
    n=int(tail)
    if not 0<=n<=MAX_LOG_TAIL:
        raise AppError("stage_log_tail_limit",400)
    since=_safe_log_time(opts["since"]) if "since" in opts else None
    until=_safe_log_time(opts["until"]) if "until" in opts else None
    return {"tail":n,
            "follow":opts.get("follow") in ("true","1"),
            "timestamps":opts.get("timestamps") in ("true","1"),
            "since":since,"until":until,
            "stdout":opts.get("stdout") not in ("false","0"),
            "stderr":opts.get("stderr") not in ("false","0")}


def _log_frames(ident,options):
    """Bounded read of a verified staging ID; no host paths or Docker writes.

    Docker CLI reads only the immutable container ID obtained from the
    provenance-checked registry. It does not expose the daemon socket.
    We encode the Docker stdout/stderr mux header expected by API clients.
    """
    if not CID.fullmatch(ident):
        raise AppError("invalid_stage_log_container",400)
    args=["docker","logs","--tail",str(options["tail"])]
    if options["timestamps"]:
        args.append("--timestamps")
    if options["follow"]:
        args.append("--follow")
    if options["since"] is not None:
        args+=["--since",options["since"]]
    if options["until"] is not None:
        args+=["--until",options["until"]]
    args.append(ident)
    result=[]
    used=0
    deadline=time.monotonic()+MAX_LOG_SECONDS
    try:
        proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                              stdin=subprocess.DEVNULL,bufsize=0)
    except OSError:
        raise AppError("stage_log_reader_unavailable",503)
    try:
        with selectors.DefaultSelector() as sel:
            sel.register(proc.stdout,selectors.EVENT_READ,1)
            sel.register(proc.stderr,selectors.EVENT_READ,2)
            while sel.get_map() and time.monotonic()<deadline and used<MAX_LOG_BYTES:
                ready=sel.select(timeout=min(.3,max(0,deadline-time.monotonic())))
                for key,_ in ready:
                    chunk=os.read(key.fd,min(4096,MAX_LOG_BYTES-used))
                    if not chunk:
                        sel.unregister(key.fileobj)
                        continue
                    if ((key.data==1 and options["stdout"]) or
                        (key.data==2 and options["stderr"])):
                        result.append(bytes([key.data,0,0,0])+
                                      struct.pack(">I",len(chunk))+chunk)
                        used+=len(chunk)
            if not options["follow"]:
                try:
                    proc.wait(timeout=.3)
                except subprocess.TimeoutExpired:
                    pass
                if proc.poll() not in (None,0):
                    raise AppError("stage_log_reader_failed",503)
            elif proc.poll() not in (None,0):
                raise AppError("stage_log_reader_failed",503)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=.8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=.8)
        proc.stdout.close()
        proc.stderr.close()
    return b"".join(result)


def _stage_logs_for_id(ident,query):
    options=_log_request(query)
    try:
        confirmed=_resolve_stage_item(ident)["Id"]
    except AppError as error:
        if error.status==404:
            raise AppError("stage_log_container_not_registered",404)
        raise
    if not _LOG_SLOTS.acquire(blocking=False):
        raise AppError("stage_log_read_capacity",429)
    try:
        return _log_frames(confirmed,options)
    finally:
        _LOG_SLOTS.release()


def _event_request(query):
    if not isinstance(query,str) or len(query)>300:
        raise AppError("invalid_stage_event_query",400)
    try:
        items=parse_qsl(query,keep_blank_values=True,strict_parsing=True,
                        max_num_fields=4)
    except ValueError:
        raise AppError("invalid_stage_event_query",400)
    opts={}
    for key,value in items:
        if key in opts or key not in ("since","until","filters"):
            raise AppError("unsupported_stage_event_query",400)
        opts[key]=value
    for key in ("since","until"):
        if key in opts and (not opts[key].isascii() or
            not opts[key].isdecimal() or len(opts[key])>11):
            raise AppError("invalid_stage_event_time",400)
    if "filters" in opts:
        try:
            filters=json.loads(opts["filters"])
        except ValueError:
            raise AppError("invalid_stage_event_filters",400)
        if not isinstance(filters,dict) or len(filters)>4 or any(
                key not in ("type","event","container","label") for key in filters):
            raise AppError("unsupported_stage_event_filters",403)
        if any(not isinstance(value,(list,dict)) for value in filters.values()):
            raise AppError("invalid_stage_event_filters",400)
    return opts


def _container_event(row,action):
    # The event emitter must use exactly the same stage-verified digest as
    # /containers/json and /images/json. Never invent a host repository tag.
    image_id=row.get("ImageID") if isinstance(row,dict) else None
    if (not isinstance(image_id,str) or not IMAGE_DIGEST.fullmatch(image_id)
        or row.get("Image")!=image_id
        or (row.get("Labels") or {}).get("osd.stage.scope")!="staging-only"):
        raise AppError("stage_broker_unverified_event_image",403)
    now=time.time()
    return {"Type":"container","Action":action,"Actor":{
        "ID":row["Id"],"Attributes":{
            "name":row["Names"][0],"image":image_id}},
        "scope":"local","time":int(now),"timeNano":int(now*1000000000),
        "id":row["Id"],"status":action,"from":image_id}


def _stats_request(query):
    if not isinstance(query,str) or len(query)>130:
        raise AppError("invalid_stage_stats_query",400)
    try:
        items=parse_qsl(query,keep_blank_values=True,strict_parsing=True,
                        max_num_fields=3)
    except ValueError:
        raise AppError("invalid_stage_stats_query",400)
    opts={}
    for key,value in items:
        if key in opts or key not in ("stream","one-shot","one_shot"):
            raise AppError("unsupported_stage_stats_query",400)
        if value not in ("1","0","true","false"):
            raise AppError("invalid_stage_stats_boolean",400)
        opts[key]=value
    return opts.get("stream","true") in ("1","true")


def _normalized_path(path):
    if not isinstance(path,str) or len(path)>450:
        return None
    parsed=urlsplit(path)
    if parsed.netloc or parsed.scheme or parsed.fragment:
        return None
    raw=PREFIX.sub("",parsed.path,count=1)
    is_log=bool(re.fullmatch(r"/containers/[a-f0-9]{12,64}/logs",raw))
    is_stats=bool(re.fullmatch(r"/containers/[a-f0-9]{12,64}/stats",raw))
    if (parsed.query and raw not in
            ("/containers/json","/images/json","/events")
            and not is_log and not is_stats):
        return None
    if raw=="/images/json" and parsed.query:
        if len(parsed.query)>90:
            return None
        try:
            params=parse_qsl(parsed.query,strict_parsing=True,
                             max_num_fields=2)
        except ValueError:
            return None
        if (len({k for k,_ in params})!=len(params)
            or any(k not in ("all","digests") or
                   v not in ("0","1","true","false") for k,v in params)):
            return None
    if raw=="/containers/json" and parsed.query:
        # no hostile filters or arbitrary user-directed Docker operations
        if not re.fullmatch(r"(?:all=(?:0|1|true|false))?",parsed.query):
            return None
    return raw


class Handler(BaseHTTPRequestHandler):
    server_version="OSD-Stage-DockerFacade/1.0"
    sys_version=""
    protocol_version="HTTP/1.1"

    def log_message(self,format,*args):
        # Socket may be accessed by untrusted app; log no caller-supplied paths.
        pass

    def _respond(self,status,payload,kind="application/json"):
        raw=(payload.encode("utf-8") if isinstance(payload,str)
             else json.dumps(payload,separators=(",",":")).encode("utf-8"))
        self.send_response(status)
        self.send_header("Content-Type",kind)
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers()
        if self.command!="HEAD":
            self.wfile.write(raw)

    def _respond_raw(self,status,raw):
        self.send_response(status)
        self.send_header("Content-Type","application/vnd.docker.raw-stream")
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Length",str(len(raw)))
        self.send_header("Connection","close")
        self.end_headers()
        self.close_connection=True
        if self.command!="HEAD":
            self.wfile.write(raw)

    def _chunked(self,payload):
        chunk=payload if isinstance(payload,bytes) else payload.encode("utf-8")
        self.wfile.write(("%x\r\n"%len(chunk)).encode("ascii")+chunk+b"\r\n")
        self.wfile.flush()

    def _events(self,query):
        _event_request(query)
        if not _EVENT_SLOTS.acquire(blocking=False):
            return self._respond(429,{"message":"stage_event_capacity"})
        try:
            # Validate full stage provenance BEFORE returning successful headers.
            rows=stage_containers()
            previous={row["Id"]:row for row in rows}
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Transfer-Encoding","chunked")
            self.send_header("Cache-Control","no-store")
            self.send_header("Connection","close")
            self.end_headers()
            self.close_connection=True
            deadline=time.monotonic()+MAX_EVENT_SECONDS
            next_heartbeat=time.monotonic()+EVENT_HEARTBEAT_SECONDS
            # Send stage-only initial state to seed the Docker event listener.
            for row in rows:
                if row["State"]=="running":
                    self._chunked(json.dumps(_container_event(row,"start"))+"\n")
            while time.monotonic()<deadline:
                time.sleep(min(3,deadline-time.monotonic()))
                if time.monotonic()>=deadline:
                    break
                latest={row["Id"]:row for row in stage_containers()}
                for ident,row in latest.items():
                    if ident not in previous:
                        self._chunked(json.dumps(_container_event(row,"start"))+"\n")
                    elif row["State"]!=previous[ident]["State"]:
                        self._chunked(json.dumps(_container_event(
                            row,"start" if row["State"]=="running" else "die"))+"\n")
                for ident,row in previous.items():
                    if ident not in latest:
                        self._chunked(json.dumps(_container_event(row,"destroy"))+"\n")
                previous=latest
                if time.monotonic()>=next_heartbeat:
                    # A JSON whitespace heartbeat prevents clients from
                    # treating an idle event stream as a disconnected engine.
                    self._chunked(b"\n")
                    next_heartbeat=time.monotonic()+EVENT_HEARTBEAT_SECONDS
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError,TimeoutError):
            self.close_connection=True
        except (OSError,AppError):
            self.close_connection=True
        finally:
            _EVENT_SLOTS.release()

    def _stats(self,reference,query):
        streaming=_stats_request(query)
        item=_resolve_stage_item(reference)
        if not _STATS_SLOTS.acquire(blocking=False):
            return self._respond(429,{"message":"stage_stats_capacity"})
        try:
            if not streaming:
                return self._respond(200,stage_stats_snapshot(item))
            first=stage_stats_snapshot(item)  # validate BEFORE HTTP 200
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Transfer-Encoding","chunked")
            self.send_header("Cache-Control","no-store")
            self.send_header("Connection","close")
            self.end_headers()
            self.close_connection=True
            deadline=time.monotonic()+MAX_STATS_SECONDS
            self._chunked(json.dumps(first)+"\n")
            while time.monotonic()<deadline:
                time.sleep(min(3,deadline-time.monotonic()))
                if time.monotonic()>=deadline:
                    break
                item=_resolve_stage_item(reference)
                self._chunked(json.dumps(stage_stats_snapshot(item))+"\n")
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError,TimeoutError):
            self.close_connection=True
        except (AppError,OSError,ValueError):
            self.close_connection=True
        finally:
            _STATS_SLOTS.release()

    def do_GET(self):
        path=_normalized_path(self.path)
        if path=="/_ping":
            return self._respond(200,"OK","text/plain")
        if path=="/version":
            return self._respond(200,{
                "Version":"osd-stage-readonly-1",
                "ApiVersion":"1.43","MinAPIVersion":"1.24",
                "Os":"linux","Arch":"amd64",
                "Platform":{"Name":"OpenServerDesk isolated staging only"},
            })
        if path=="/events":
            try:
                return self._events(urlsplit(self.path).query)
            except AppError as err:
                return self._respond(err.status,{"message":err.message})
            except (OSError,ValueError):
                return self._respond(503,{"message":"stage_events_unavailable"})
        if path=="/info":
            try:
                rows=stage_containers()
            except (AppError,OSError,ValueError):
                return self._respond(503,{"message":"stage_inventory_unavailable"})
            return self._respond(200,{"Name":"osd-stage-only",
                "Containers":len(rows),
                "ContainersRunning":sum(r["State"]=="running" for r in rows),
                "Images":len(stage_images(rows)),"ID":"no-host-runtime",
                "Driver":"stage-only","SecurityOptions":["stage-only-read-only"]})
        if path=="/containers/json":
            try:
                return self._respond(200,stage_containers())
            except (AppError,OSError,ValueError):
                return self._respond(503,{"message":"stage_inventory_unavailable"})
        if path=="/images/json":
            try:
                return self._respond(200,stage_images())
            except (AppError,OSError,ValueError):
                return self._respond(503,{"message":"stage_image_inventory_unavailable"})
        if path and re.fullmatch(
                r"/images/(?:sha256:)?[a-f0-9]{64}/json",path):
            reference=path[len("/images/"):-len("/json")]
            try:
                item=_resolve_stage_image(reference)
                return self._respond(200,{
                    "Id":item["Id"],"RepoTags":item["RepoTags"],
                    "RepoDigests":item["RepoDigests"],"Parent":"",
                    "Labels":item["Labels"],"Size":item["Size"],
                    "VirtualSize":item["VirtualSize"],
                    "Config":{"Labels":item["Labels"]},
                    "Os":"linux","Architecture":"amd64",
                })
            except AppError as err:
                return self._respond(err.status,{"message":err.message})
            except (OSError,ValueError):
                return self._respond(503,{"message":"stage_image_inventory_unavailable"})
        if path and re.fullmatch(r"/containers/[a-f0-9]{12,64}/stats",path):
            reference=path[len("/containers/"):-len("/stats")]
            try:
                return self._stats(reference,urlsplit(self.path).query)
            except AppError as err:
                return self._respond(err.status,{"message":err.message})
            except (OSError,ValueError,subprocess.SubprocessError):
                return self._respond(503,{"message":"stage_stats_reader_unavailable"})
        if path and re.fullmatch(r"/containers/[a-f0-9]{12,64}/logs",path):
            ident=path[len("/containers/"):-len("/logs")]
            try:
                body=_stage_logs_for_id(ident,urlsplit(self.path).query)
                return self._respond_raw(200,body)
            except AppError as err:
                return self._respond(err.status,{"message":err.message})
            except (OSError,ValueError,subprocess.SubprocessError):
                return self._respond(503,{"message":"stage_log_reader_unavailable"})
        if path and path.startswith("/containers/") and path.endswith("/json"):
            ident=path[len("/containers/"):-len("/json")]
            try:
                match=_resolve_stage_item(ident)
            except AppError as error:
                return self._respond(error.status,{"message":error.message})
            except (OSError,ValueError):
                return self._respond(503,{"message":"stage_inventory_unavailable"})
            return self._respond(200,{
                "Id":match["Id"],"Name":match["Names"][0],
                "Image":match["ImageID"],
                "Config":{"Image":match["Image"],"Labels":match["Labels"]},
                "State":{"Running":match["State"]=="running",
                         "Status":match["State"]},
                "Mounts":[],"NetworkSettings":{"Networks":{}},
                "HostConfig":{"Privileged":False},
            })
        return self._respond(403,{"message":"operation_not_supported"})

    def do_HEAD(self):
        return self.do_GET()

    def do_POST(self):
        self.close_connection=True
        return self._respond(403,{"message":"read_only"})

    do_PUT=do_POST
    do_PATCH=do_POST
    do_DELETE=do_POST


class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
    daemon_threads=True
    allow_reuse_address=False
    request_queue_size=20

    def __init__(self,*args,**kwargs):
        self._slots=threading.BoundedSemaphore(16)
        super().__init__(*args,**kwargs)

    def process_request(self,request,client_address):
        if not self._slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request,client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self,request,client_address):
        try:
            super().process_request_thread(request,client_address)
        finally:
            self._slots.release()


def _activated_systemd_socket():
    """Borrow PID-verified systemd fd 3, preserving the mounted socket inode."""
    fds=os.environ.get("LISTEN_FDS")
    if not fds:
        return None
    pid=os.environ.get("LISTEN_PID","")
    if fds!="1" or pid!=str(os.getpid()):
        raise RuntimeError("broker_untrusted_socket_activation")
    accepted=socket.fromfd(3,socket.AF_UNIX,socket.SOCK_STREAM)
    try:
        if (accepted.family!=socket.AF_UNIX or
            accepted.getsockname()!=str(SOCKET_PATH) or
            accepted.getsockopt(socket.SOL_SOCKET,socket.SO_ACCEPTCONN)!=1):
            raise RuntimeError("broker_socket_activation_mismatch")
        stat_info=SOCKET_PATH.lstat()
        if (not stat.S_ISSOCK(stat_info.st_mode) or stat_info.st_uid!=1000
            or stat_info.st_mode & 0o077):
            raise RuntimeError("broker_socket_activation_permissions")
        return accepted
    except Exception:
        accepted.close()
        raise


def serve_forever():
    if os.geteuid()!=1000:
        raise RuntimeError("broker_requires_andre_uid_1000")
    if SOCKET_ROOT.is_symlink():
        raise RuntimeError("broker_untrusted_socket_root")
    SOCKET_ROOT.mkdir(mode=0o700,exist_ok=True)
    if SOCKET_ROOT.stat().st_uid!=1000 or SOCKET_ROOT.stat().st_mode & 0o077:
        raise RuntimeError("broker_socket_root_permissions")
    activated=_activated_systemd_socket()
    if activated is not None:
        # The socket unit owns this inode for the lifetime of the .socket
        # service. Broker restarts must NOT unlink/rebind the mounted socket.
        with Server(str(SOCKET_PATH),Handler,bind_and_activate=False) as server:
            server.socket.close()  # replace unbound placeholder with fd 3
            server.socket=activated
            server.serve_forever(poll_interval=0.2)
        return
    try:
        st=SOCKET_PATH.lstat()
    except FileNotFoundError:
        st=None
    if st is not None:
        if not stat.S_ISSOCK(st.st_mode) or st.st_uid!=1000:
            raise RuntimeError("broker_untrusted_socket_file")
        # A detached SIGTERM can leave a stale socket inode. Reclaim only
        # a socket that is proved NOT to have a listening peer.
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(0.3)
            try:
                client.connect(str(SOCKET_PATH))
            except ConnectionRefusedError:
                SOCKET_PATH.unlink()
            else:
                raise RuntimeError("broker_already_listening")
    # UnixSocket leaves an inode file: validate before removing on shutdown.
    with Server(str(SOCKET_PATH),Handler) as server:
        os.chmod(SOCKET_PATH,0o600)
        try:
            server.serve_forever(poll_interval=0.2)
        finally:
            if SOCKET_PATH.is_socket() and SOCKET_PATH.stat().st_uid==1000:
                SOCKET_PATH.unlink()


if __name__=="__main__":
    serve_forever()
