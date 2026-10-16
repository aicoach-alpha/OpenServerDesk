"""Read-only CasaOS v1 Compose store catalog, no access to application user data.

Only the LOCAL CasaOS platform's installed App Store catalogue is parsed.
Never follows symlinks, touches app volumes, scans external disks or pulls an
untrusted Compose image. Metadata is sanitized, not a Docker install payload.
"""
from __future__ import annotations
import os
import re
import stat
import threading
import time
from pathlib import Path
import yaml

# LibYAML's safe implementation accepts only standard YAML data types.
# Fallback remains safe when the optional C extension is not installed.
SAFE_LOADER=getattr(yaml,"CSafeLoader",yaml.SafeLoader)

STORE_ROOT = Path("/var/lib/casaos/appstore")
ALLOWED_STORES = {"default", "github.com", "casaos.app"}
COMPOSE_FILES = {"docker-compose.yml", "docker-compose.yaml"}
MAX_COMPOSE_BYTES = 262144
MAX_FILES = 1800
TTL_SECONDS = 120
MAX_APPS = 1500
ID_RE = re.compile(r"^[a-zA-Z0-9_.:-]{1,110}$")
_TEXT_LIMIT = 200
_state = {"until":0, "data":None, "paths":{}}
_guard = threading.Lock()

def _text(x, limit=_TEXT_LIMIT):
    if isinstance(x, dict):
        x = x.get("en_US") or x.get("en") or next(
            (v for v in x.values() if isinstance(v,str)), "")
    if not isinstance(x, str):
        return ""
    return "".join(c for c in x.strip() if c.isprintable())[:limit]

def _safe_path(file, root):
    if not file.is_relative_to(root):
        return False
    cur=file
    while cur != root:
        if cur.is_symlink():
            return False
        cur=cur.parent
    return not root.is_symlink()

def _source_files(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError("CasaOS store cache unavailable")
    yielded=0
    for namespace in sorted(root.iterdir()):
        if namespace.name not in ALLOWED_STORES:
            continue
        if namespace.is_symlink() or not namespace.is_dir():
            continue
        for base, folders, files in os.walk(namespace, followlinks=False):
            parent=Path(base)
            # Only catalogue metadata inside the chosen platform store.
            if not _safe_path(parent,root):
                raise ValueError("untrusted appstore metadata directory")
            folders[:]=sorted(n for n in folders if not (parent/n).is_symlink())
            for filename in sorted(files):
                if filename not in COMPOSE_FILES:
                    continue
                path=parent/filename
                if not _safe_path(path,root):
                    continue
                st=path.lstat()
                if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_COMPOSE_BYTES:
                    continue
                yielded+=1
                if yielded>MAX_FILES:
                    raise ValueError("excessive CasaOS store records")
                yield namespace.name, path

def _parse(namespace, path):
    try:
        with path.open("r",encoding="utf-8") as f:
            doc=yaml.load(f,Loader=SAFE_LOADER)
    except (OSError, UnicodeError, yaml.YAMLError):
        return None
    if not isinstance(doc,dict) or not isinstance(doc.get("services"),dict):
        return None
    meta=doc.get("x-casaos") or {}
    if not isinstance(meta,dict):
        meta={}
    name=_text(doc.get("name")) or path.parent.name
    identifier=_text(meta.get("id")) or path.parent.name
    identifier=f"{namespace}:{identifier}"
    if not ID_RE.fullmatch(identifier):
        return None
    title=_text(meta.get("title")) or path.parent.name
    if not title:
        return None
    services=doc["services"]
    if not services or len(services)>32:
        return None
    categories=_text(meta.get("category"),80) or "Other"
    risk={
        "uses_ports":any(bool(s.get("ports")) for s in services.values() if isinstance(s,dict)),
        "uses_bind_or_volume":any(bool(s.get("volumes")) for s in services.values() if isinstance(s,dict)),
        "host_network":any(s.get("network_mode") == "host" for s in services.values() if isinstance(s,dict)),
        "privileged":any(s.get("privileged") is True for s in services.values() if isinstance(s,dict)),
    }
    return {
        "id":identifier, "title":title,
        "store":namespace, "category":categories,
        "tagline":_text(meta.get("tagline")),
        "description":_text(meta.get("description"),350),
        "version":_text(meta.get("version"),48),
        "service_count":len(services),
        "compatibility":{
            "metadata_read":True,
            "staging_install_verified":False,
            **risk,
        },
    }

def _index(root, with_paths=False):
    entries={}
    paths={}
    scanned=0
    for namespace, path in _source_files(root):
        scanned+=1
        item=_parse(namespace,path)
        if item is None:
            continue
        # Namespaces can include multiple stores; stable path disambiguation.
        key=item["id"]
        if key in entries:
            suffix=path.parent.name.lower()
            key=f"{namespace}:{suffix}"
            item["id"]=key
        if key in entries or not ID_RE.fullmatch(key):
            continue
        entries[key]=item
        if with_paths:
            # Private index only: never expose CasaOS paths through the API.
            st=path.lstat()
            paths[key]=(path,st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
        if len(entries)>MAX_APPS:
            raise ValueError("excessive indexed apps")
    rows=sorted(entries.values(),key=lambda e:(e["title"].casefold(),e["store"],e["id"]))
    counts={}
    for e in rows:
        counts[e["store"]]=counts.get(e["store"],0)+1
    public={"source":"existing_casaos_appstore_cache_readonly",
            "catalog_format":"legacy_compose_x-casaos",
            "definitions_examined":scanned,
            "app_count":len(rows),"store_counts":counts,
            "categories":sorted({e["category"] for e in rows}),
            "apps":rows,
            "production_modified":False,
            "nextcloud_user_data_inspected":False,
            "app_install_enabled":False,
            "migration_allowed":False}
    return (public,paths) if with_paths else public

def catalog(root=STORE_ROOT):
    if root!=STORE_ROOT:
        return _index(root)
    with _guard:
        if _state["data"] is None or time.monotonic()>=_state["until"]:
            result,path_index=_index(root,with_paths=True)
            _state["data"]=result
            _state["paths"]=path_index
            _state["until"]=time.monotonic()+TTL_SECONDS
        return _state["data"]

def indexed_definition(app_id):
    """Resolve exactly one cached CasaOS catalogue metadata path in O(1).

    The metadata cache is shared with the public catalogue but internal path
    references are never returned via HTTP. Any file change fails closed and
    invalidates the cache; we do not follow symlinks or application data.
    """
    if not isinstance(app_id,str) or not ID_RE.fullmatch(app_id):
        raise ValueError("invalid store app identifier")
    public=catalog()
    known=next((entry for entry in public["apps"] if entry["id"]==app_id),None)
    if known is None:
        raise ValueError("unknown store app")
    with _guard:
        candidate=_state["paths"].get(app_id)
    if candidate is None:
        raise ValueError("catalogue path not indexed")
    path,dev,ino,size,mtime,ctime=candidate
    if not _safe_path(path,STORE_ROOT):
        raise ValueError("unsafe store metadata path")
    st=path.lstat()
    if (not stat.S_ISREG(st.st_mode) or
        (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)!=
        (dev,ino,size,mtime,ctime)):
        with _guard:
            _state["until"]=0
        raise ValueError("store metadata changed; retry")
    return known,path

def compatibility(app_id):
    if not isinstance(app_id,str) or not ID_RE.fullmatch(app_id):
        raise ValueError("invalid store app identifier")
    item=next((v for v in catalog()["apps"] if v["id"]==app_id),None)
    if item is None:
        raise ValueError("unknown store app")
    return {"id":item["id"],"title":item["title"],"store":item["store"],
            "service_count":item["service_count"],"compatibility":item["compatibility"],
            "can_install_in_staging":False,
            "reason":"full_app_runtime_network_ports_and_volume_isolation_not_yet_verified",
            "production_modified":False,"migration_allowed":False}
