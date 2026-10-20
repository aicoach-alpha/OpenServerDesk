"""Docker API *compatibility facade* for explicitly approved staging apps.

This is NOT a Docker socket proxy. It never forwards bytes to the real Docker
daemon, offers no host Docker API, and returns only records obtained after the
OpenServerDesk staging registry and container provenance checks. By default
all Docker-like endpoints except the few safe GET paths are denied.
"""
from __future__ import annotations

import json
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
from stage_host_socket import SOCKET_ROOT, SOCKET_PATH
CID=re.compile(r"[a-f0-9]{64}\Z")
PROJECT=re.compile(r"osd-compiled-[a-f0-9]{12}\Z")
PREFIX=re.compile(r"/v[0-9]{1,2}\.[0-9]{1,2}(?=/|$)")
MAX_CONTAINERS=16
MAX_LOG_BYTES=64*1024
MAX_LOG_TAIL=160
MAX_LOG_SECONDS=5.5
_LOG_SLOTS=threading.BoundedSemaphore(2)


def stage_containers():
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
        _,services=_current(project,entry)
        for name,item in sorted(services.items()):
            ident=item.get("id")
            if not isinstance(ident,str) or not CID.fullmatch(ident):
                raise AppError("stage_broker_invalid_container",503)
            result.append({
                "Id":ident,
                "Names":["/osd-stage-"+project+"-"+name],
                "Image":"openserverdesk/stage-only",
                "ImageID":"redacted-stage-only",
                "State":"running" if item["running"] else "exited",
                "Status":"Stage app (isolated)",
                "Labels":{"osd.stage.scope":"staging-only",
                          "osd.stage.project":project},
                "Ports":[],
                "Mounts":[],
                "NetworkSettings":{"Networks":{}},
            })
            if len(result)>MAX_CONTAINERS:
                raise AppError("stage_broker_container_limit",503)
    return result


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
    for key in ("since","until"):
        if key in opts and (not opts[key].isascii() or
            not opts[key].isdecimal() or len(opts[key])>11):
            raise AppError("invalid_stage_log_timestamp",400)
    return {"tail":n,
            "follow":opts.get("follow") in ("true","1"),
            "timestamps":opts.get("timestamps") in ("true","1"),
            "since":opts.get("since"),"until":opts.get("until"),
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
    if not CID.fullmatch(ident):
        raise AppError("invalid_stage_log_container",400)
    if ident not in {x["Id"] for x in stage_containers()}:
        raise AppError("stage_log_container_not_registered",404)
    if not _LOG_SLOTS.acquire(blocking=False):
        raise AppError("stage_log_read_capacity",429)
    try:
        return _log_frames(ident,options)
    finally:
        _LOG_SLOTS.release()


def _normalized_path(path):
    if not isinstance(path,str) or len(path)>450:
        return None
    parsed=urlsplit(path)
    if parsed.netloc or parsed.scheme or parsed.fragment:
        return None
    raw=PREFIX.sub("",parsed.path,count=1)
    is_log=bool(re.fullmatch(r"/containers/[a-f0-9]{64}/logs",raw))
    if parsed.query and raw!="/containers/json" and not is_log:
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
        if path=="/info":
            try:
                rows=stage_containers()
            except (AppError,OSError,ValueError):
                return self._respond(503,{"message":"stage_inventory_unavailable"})
            return self._respond(200,{"Name":"osd-stage-only",
                "Containers":len(rows),
                "ContainersRunning":sum(r["State"]=="running" for r in rows),
                "Images":0,"ID":"no-host-runtime",
                "Driver":"stage-only","SecurityOptions":["stage-only-read-only"]})
        if path=="/containers/json":
            try:
                return self._respond(200,stage_containers())
            except (AppError,OSError,ValueError):
                return self._respond(503,{"message":"stage_inventory_unavailable"})
        if path and re.fullmatch(r"/containers/[a-f0-9]{64}/logs",path):
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
            if not CID.fullmatch(ident):
                return self._respond(404,{"message":"not_found"})
            try:
                match=next((x for x in stage_containers()
                            if x["Id"]==ident),None)
            except (AppError,OSError,ValueError):
                return self._respond(503,{"message":"stage_inventory_unavailable"})
            if match is None:
                return self._respond(404,{"message":"not_found"})
            return self._respond(200,{
                "Id":match["Id"],"Name":match["Names"][0],
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
    request_queue_size=12

    def __init__(self,*args,**kwargs):
        self._slots=threading.BoundedSemaphore(8)
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


def serve_forever():
    if os.geteuid()!=1000:
        raise RuntimeError("broker_requires_andre_uid_1000")
    if SOCKET_ROOT.is_symlink():
        raise RuntimeError("broker_untrusted_socket_root")
    SOCKET_ROOT.mkdir(mode=0o700,exist_ok=True)
    if SOCKET_ROOT.stat().st_uid!=1000 or SOCKET_ROOT.stat().st_mode & 0o077:
        raise RuntimeError("broker_socket_root_permissions")
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
