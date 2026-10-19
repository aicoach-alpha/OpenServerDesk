"""Authenticated, tightly scoped MySpeed staging web gateway.

No arbitrary URL input: only the registered, provenance-verified MySpeed
staging project, and its published server-local loopback web port.
Stage session cookies do not grant access to the operator API.
"""
from __future__ import annotations
import http.client
import re
import secrets
import threading
import time
from http.cookies import SimpleCookie
from urllib.parse import unquote, urlsplit
from stage_apps import AppError
from stage_store_runtime import (
    listing, PROJECT, _projects, _current, _stage_private_endpoint)
from stage_qui_pilot import APP as QUI_APP

PREFIX="/stage-app/"
COOKIE="osd_my_speed_preview"
TTL=600
MAX_SESSIONS=16
MAX_BODY=1024*1024
MAX_RESPONSE=8*1024*1024
_sessions={}
_lock=threading.Lock()
_ALLOWED_METHODS={"GET","HEAD","POST","PUT","PATCH","DELETE"}
_ALLOWED_TYPES=("text/","application/json","application/javascript",
                "application/manifest+json","image/","font/","application/font-",
                "application/octet-stream")
_REWRITE_PREFIXES=("assets/","api/","api","manifest.json","registerSW.js","sw.js",
                   "favicon.ico","socket.io/")
_SEGMENT=re.compile(r"[A-Za-z0-9._~!$&'()+,;=:@%/-]*\Z")


def _matching(project):
    if not isinstance(project,str) or not PROJECT.fullmatch(project):
        raise AppError("invalid_stage_web_project",400)
    state=listing()
    app=next((a for a in state["apps"] if a["project"]==project),None)
    if app is None or not app.get("all_running"):
        raise AppError("stage_web_app_unavailable",404)
    if app["app_id"]==QUI_APP and app.get("outbound_network_pilot") is False:
        values=_projects()
        entry=values.get(project)
        if entry is None or entry.get("app_id")!=QUI_APP:
            raise AppError("stage_web_qui_project_invalid",403)
        manifest,services=_current(project,entry)
        return _stage_private_endpoint(project,manifest,entry["owner"],services)
    if app["app_id"]!="default:MySpeed" or app.get("outbound_network_pilot") is not True:
        raise AppError("stage_web_app_unavailable",404)
    url=app.get("web_url")
    if not isinstance(url,str):
        raise AppError("stage_web_port_missing",503)
    m=re.fullmatch(r"http://127\.0\.0\.1:(18[7-9][0-9]{2}|19[0-9]{3})",url)
    if not m:
        raise AppError("stage_web_loopback_invalid",403)
    return int(m.group(1))


def _session_cleanup(now):
    for token,entry in list(_sessions.items()):
        if entry[1]<=now:
            del _sessions[token]


def issue(project):
    """Only caller after successful write-authorized stage API authentication."""
    target=_matching(project)
    now=time.monotonic()
    with _lock:
        _session_cleanup(now)
        if len(_sessions)>=MAX_SESSIONS:
            raise AppError("stage_web_session_capacity",429)
        key=secrets.token_urlsafe(32)
        _sessions[key]=(project,now+TTL)
    path=PREFIX+project+"/"
    cookie=(COOKIE+"="+key+"; Path="+path+
            "; Max-Age="+str(TTL)+"; HttpOnly; SameSite=Strict")
    return {"entry":path,"expires_in_seconds":TTL,
            "scope":("authenticated_qui_stage_only" if isinstance(target,tuple)
                     else "authenticated_myspeed_stage_only"),
            "production_mutation_allowed":False},cookie


def _cookie(project,header):
    jar=SimpleCookie()
    try:
        jar.load(header or "")
    except Exception:
        raise AppError("invalid_stage_web_cookie",401)
    value=jar.get(COOKIE)
    token=value.value if value is not None else ""
    now=time.monotonic()
    with _lock:
        _session_cleanup(now)
        entry=_sessions.get(token)
        if entry is None or entry[0]!=project:
            raise AppError("stage_web_session_expired",401)
    return True


def parse_route(uri):
    if not isinstance(uri,str) or len(uri)>4096:
        raise AppError("invalid_stage_web_path",400)
    parsed=urlsplit(uri)
    path=parsed.path
    m=re.fullmatch(r"/stage-app/(osd-compiled-[0-9a-f]{12})(/.*)?",path)
    if not m or parsed.fragment or len(parsed.query)>2048:
        raise AppError("invalid_stage_web_path",400)
    sub=m.group(2) or "/"
    decoded=unquote(sub)
    if (not _SEGMENT.fullmatch(sub) or any(ord(c)<32 for c in decoded)
            or "\\" in decoded or "//" in decoded
            or any(x in ("..",".") for x in decoded.split("/"))
            or "%2f" in sub.lower() or "%5c" in sub.lower()):
        raise AppError("invalid_stage_web_path",400)
    return m.group(1),sub+("?" + parsed.query if parsed.query else "")


def rewrite(body,content_type,project):
    """Rewrite root asset/API references from this specific tested SPA.

    This is NOT a generic browser proxy for untrusted arbitrary applications.
    """
    base=PREFIX+project+"/"
    typ=content_type.lower().split(";",1)[0].strip()
    if typ not in ("text/html","text/css","application/javascript",
                   "text/javascript","application/manifest+json"):
        return body
    value=body.decode("utf-8","replace")
    if typ in ("text/html","application/javascript","text/javascript",
               "application/manifest+json"):
        for quote in ('"',"'"):
            for prefix in _REWRITE_PREFIXES:
                value=value.replace(quote+"/"+prefix,quote+base+prefix)
    if typ=="text/css":
        value=(value.replace("url(/assets/","url("+base+"assets/")
               .replace('url("/assets/','url("'+base+"assets/")
               .replace("url('/assets/","url('"+base+"assets/"))
    return value.encode("utf-8")


def _safe_headers(headers):
    return {k:v for k,v in headers.items()
            if k.lower() in ("accept","content-type","accept-language") and len(v)<=256}


def proxy(method,uri,cookies,headers,body=b""):
    if method not in _ALLOWED_METHODS:
        raise AppError("stage_web_method_disabled",405)
    project,route=parse_route(uri)
    _cookie(project,cookies)
    if len(body)>MAX_BODY:
        raise AppError("stage_web_request_too_large",413)
    target=_matching(project)
    hostname,port=target if isinstance(target,tuple) else ("127.0.0.1",target)
    if method not in ("GET","HEAD"):
        origin=headers.get("Origin")
        if origin is None:
            raise AppError("stage_web_origin_required",403)
        if origin not in ("http://127.0.0.1:18690","http://localhost:18690"):
            raise AppError("stage_web_origin_rejected",403)
    if route.startswith("/registerSW.js") or route.startswith("/sw.js"):
        return 200,"application/javascript",b"/* staging service workers disabled */",{}
    connection=http.client.HTTPConnection(hostname,port,timeout=9)
    try:
        forwarded=_safe_headers(headers)
        forwarded["Accept-Encoding"]="identity"
        forwarded["Host"]="localhost:"+str(port)
        connection.request(method,route,body=body if method not in ("GET","HEAD") else None,
                           headers=forwarded)
        response=connection.getresponse()
        if response.getheader("Content-Encoding"):
            raise AppError("stage_web_compressed_response_rejected",502)
        length=response.getheader("Content-Length")
        if length:
            try:
                if int(length)>MAX_RESPONSE:
                    raise AppError("stage_web_response_too_large",502)
            except ValueError:
                raise AppError("stage_web_invalid_response",502)
        data=response.read(MAX_RESPONSE+1)
        if len(data)>MAX_RESPONSE:
            raise AppError("stage_web_response_too_large",502)
        ctype=response.getheader("Content-Type") or "application/octet-stream"
        if not ctype.lower().startswith(_ALLOWED_TYPES):
            raise AppError("stage_web_response_type_rejected",502)
        other={}
        location=response.getheader("Location")
        if location:
            if not location.startswith("/") or location.startswith("//"):
                raise AppError("stage_web_external_redirect_blocked",502)
            other["Location"]=PREFIX+project+location
        payload=rewrite(data,ctype,project)
        return response.status,ctype,payload,other
    except (OSError,TimeoutError,http.client.HTTPException) as err:
        raise AppError("stage_web_upstream_unavailable",502) from err
    finally:
        connection.close()
