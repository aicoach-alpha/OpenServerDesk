"""Crash-recoverable snapshots of compiler-owned staging volumes only.

Checkpoint/restore require ALL owned containers stopped. The original
production Compose paths and Nextcloud HDD are NEVER traversed or mounted.
"""
from __future__ import annotations
import hashlib, json, os, re, secrets, shutil, sqlite3, stat
from pathlib import Path
from urllib.parse import quote
from stage_apps import AppError
from stage_store_compiler import STAGE
from stage_host_socket import is_facade_mount
from stage_postgres_integrity import is_qui_pg, verify as verify_pg_cold

ROOT=Path(STAGE)
CP=re.compile(r"data-[0-9a-f]{12}\Z")
LIMIT_FILES=12000
LIMIT_BYTES=128*1024*1024
LIMIT_SNAPSHOTS=4

def _dir(project):
    if not isinstance(project,str) or not re.fullmatch(r"osd-compiled-[a-f0-9]{12}",project):
        raise AppError("invalid_stage_data_project",400)
    root=ROOT/project
    if not root.is_dir() or root.is_symlink() or root.stat().st_dev!=ROOT.stat().st_dev:
        raise AppError("unsafe_stage_data_root",403)
    return root

def _volumes(project,manifest):
    root=_dir(project)
    out=[]
    for service,config in sorted(manifest["services"].items()):
        for i,m in enumerate(config.get("volumes",[])):
            if is_facade_mount(m):
                continue  # socket is a capability, never stage user data
            rel=f"{service}/volume-{i}"
            path=root/rel
            if (m.get("source")!=str(path) or not path.is_dir() or path.is_symlink()
                    or path.stat().st_dev!=ROOT.stat().st_dev):
                raise AppError("unsafe_stage_data_volume",403)
            out.append((rel,path))
    return out

def _stopped(services):
    if any(s["running"] for s in services.values()):
        raise AppError("stop_all_stage_services_for_data_checkpoint",409)

def _scan(src,quota):
    # No symlink, hardlink, special file, nested mount or cross-device access.
    st=src.lstat()
    if st.st_dev!=ROOT.stat().st_dev:
        raise AppError("cross_device_stage_data_rejected",403)
    quota[0]+=1
    if quota[0]>LIMIT_FILES:
        raise AppError("stage_data_file_count_limit",409)
    if stat.S_ISDIR(st.st_mode):
        for item in src.iterdir():
            _scan(item,quota)
    elif stat.S_ISREG(st.st_mode) and st.st_nlink==1:
        quota[1]+=st.st_size
        if quota[1]>LIMIT_BYTES:
            raise AppError("stage_data_size_limit",409)
    else:
        raise AppError("unsafe_stage_data_entry",403)

def _digest_tree(root):
    """Deterministic file-content digest, including relative paths and file sizes.

    Checks staging-owned snapshot trees only. Reject special files/symlinks
    and prevent changed copied bytes from passing restore verification.
    """
    root=Path(root)
    _scan(root,[0,0])
    h=hashlib.sha256()
    count=0
    for path in sorted(root.rglob("*")):
        rel=path.relative_to(root).as_posix().encode("utf-8")
        mode=path.lstat().st_mode
        if stat.S_ISDIR(mode):
            h.update(b"D"+len(rel).to_bytes(4,"big")+rel)
        elif stat.S_ISREG(mode):
            h.update(b"F"+len(rel).to_bytes(4,"big")+rel)
            size=path.stat().st_size
            h.update(size.to_bytes(8,"big"))
            with path.open("rb") as f:
                for block in iter(lambda:f.read(1024*1024),b""):
                    h.update(block)
            count+=1
        else:
            raise AppError("unsafe_stage_data_entry",403)
    return {"sha256":h.hexdigest(),"files":count}

SQLITE_MAGIC=b"SQLite format 3\0"
SQLITE_SUFFIXES=(".sqlite",".sqlite3",".db")

def _sqlite_check(root):
    """Quick-check cold, staging-owned SQLite files; never inspect host paths.

    This is SQLite physical-consistency evidence only, not a guarantee of
    application-level transactions or PostgreSQL/MySQL recovery.
    """
    root=Path(root)
    _scan(root,[0,0])
    checked=0
    for file in sorted(root.rglob("*")):
        if not file.is_file():
            continue
        with file.open("rb") as stream:
            header=stream.read(16)
        named=file.name.lower().endswith(SQLITE_SUFFIXES)
        if not named and header!=SQLITE_MAGIC:
            continue
        if header!=SQLITE_MAGIC:
            raise AppError("stage_sqlite_invalid_header",409)
        # A cold snapshot containing outstanding WAL or journal transactions
        # cannot be independently verified using a single immutable DB file.
        for suffix in ("-wal","-journal"):
            sidecar=Path(str(file)+suffix)
            if sidecar.exists() or sidecar.is_symlink():
                if sidecar.is_symlink() or not sidecar.is_file() or sidecar.stat().st_size:
                    raise AppError("stage_sqlite_uncheckpointed_journal",409)
        uri="file:"+quote(str(file),safe="/")+"?mode=ro&immutable=1"
        try:
            con=sqlite3.connect(uri,uri=True,timeout=2)
            try:
                con.execute("PRAGMA query_only=ON")
                result=con.execute("PRAGMA quick_check(1)").fetchall()
            finally:
                con.close()
        except (sqlite3.DatabaseError,OSError,ValueError) as err:
            raise AppError("stage_sqlite_integrity_failed",409) from err
        if result!=[("ok",)]:
            raise AppError("stage_sqlite_integrity_failed",409)
        checked+=1
    return checked

def _safe_copy(src,dst):
    _scan(src,[0,0])
    def copy_file(a,b):
        if Path(a).is_symlink():
            raise AppError("unsafe_stage_data_symlink",403)
        shutil.copy2(a,b)
        return b
    shutil.copytree(src,dst,symlinks=False,copy_function=copy_file)

def _sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def _write(path,doc):
    tmp=path.parent/(".stage-data-"+secrets.token_hex(6))
    try:
        with tmp.open("x") as f:
            json.dump(doc,f,sort_keys=True)
            f.flush();os.fsync(f.fileno())
        tmp.chmod(0o600)
        os.replace(tmp,path);_sync(path.parent)
    finally:tmp.unlink(missing_ok=True)

def _checkpoints(project):
    root=_dir(project)/"data-checkpoints"
    if root.is_symlink():raise AppError("unsafe_stage_checkpoint_dir",403)
    root.mkdir(mode=0o700,exist_ok=True)
    if root.stat().st_mode&0o077 or root.stat().st_dev!=ROOT.stat().st_dev:
        raise AppError("unsafe_stage_checkpoint_dir",403)
    return root

def listing(project,manifest):
    _volumes(project,manifest)
    root=_checkpoints(project)
    return [p.name for p in sorted(root.iterdir())
            if CP.fullmatch(p.name) and p.is_dir() and not p.is_symlink()]

def delete_checkpoint(project,manifest,name):
    """Delete one explicitly selected stage-only backup, never application data.

    Refuse any deletion while a restore or online recovery journal exists.
    The snapshot is validated and its directory remains under the stage
    checkpoint root on the same filesystem.
    """
    _volumes(project,manifest)
    if not isinstance(name,str) or not CP.fullmatch(name):
        raise AppError("invalid_stage_checkpoint",400)
    project_root=_dir(project)
    for file in ("online-data-pending.json","data-restore-pending.json","pending.json"):
        entry=project_root/file
        if entry.exists() or entry.is_symlink():
            raise AppError("stage_checkpoint_in_use_by_recovery",409)
    linked=project_root/"previous-data.json"
    if linked.is_symlink():
        raise AppError("unsafe_stage_version_link",403)
    if linked.exists():
        if not linked.is_file() or linked.stat().st_size>1024:
            raise AppError("unsafe_stage_version_link",403)
        try:doc=json.loads(linked.read_text())
        except (ValueError,OSError):
            raise AppError("unsafe_stage_version_link",403)
        if isinstance(doc,dict) and doc.get("checkpoint")==name:
            raise AppError("stage_checkpoint_pinned_for_rollback",409)
    root=_checkpoints(project)
    snapshot=root/name
    if (snapshot.is_symlink() or not snapshot.is_dir()
            or snapshot.stat().st_dev!=ROOT.stat().st_dev):
        raise AppError("unknown_stage_checkpoint",404)
    _validate_snapshot(project,manifest,name)
    shutil.rmtree(snapshot)
    _sync(root)
    return {"operation":"checkpoint_deleted","checkpoint":name,
            "remaining":len(listing(project,manifest)),
            "production_mutation_allowed":False}

def _save(project,manifest):
    sources=_volumes(project,manifest)
    root=_checkpoints(project)
    if len(listing(project,manifest))>=LIMIT_SNAPSHOTS:
        raise AppError("stage_checkpoint_capacity",409)
    name="data-"+secrets.token_hex(6)
    tmp=root/(".building-"+name)
    tmp.mkdir(mode=0o700)
    try:
        limit=[0,0]
        for rel,source in sources:
            _scan(source,limit)
            target=tmp/"volumes"/rel
            target.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
            _safe_copy(source,target)
        digests={rel:_digest_tree(tmp/"volumes"/rel) for rel,_ in sources}
        sqlite_count=sum(_sqlite_check(tmp/"volumes"/rel) for rel,_ in sources)
        postgres_cold=verify_pg_cold(
            project,manifest,tmp/"volumes"/"postgres"/"volume-0",ROOT)
        _write(tmp/"manifest.json",{"version":4 if postgres_cold else 3,
            "id":name,"volumes":[rel for rel,_ in sources],
            "integrity":digests,
            "sqlite_files_verified":sqlite_count,
            "postgresql_cold_verified":postgres_cold,
            "count":limit[0],"bytes":limit[1]})
        os.replace(tmp,root/name)
        _sync(root)
    except Exception:
        shutil.rmtree(tmp,ignore_errors=True)
        raise
    return name

def checkpoint(project,manifest,services):
    _stopped(services)
    if (_dir(project)/"data-restore-pending.json").exists():
        raise AppError("stage_data_recovery_required",409)
    name=_save(project,manifest)
    evidence=json.loads((_checkpoints(project)/name/"manifest.json").read_text())
    return {"operation":"checkpoint","checkpoint":name,
            "sqlite_quick_check_passed":True,
            "sqlite_files_verified":evidence["sqlite_files_verified"],
            "postgresql_cold_verified":evidence.get("postgresql_cold_verified") is True,
            "production_mutation_allowed":False,"database_integrity_verified":False}

def _validate_snapshot(project,manifest,name):
    if not isinstance(name,str) or not CP.fullmatch(name):
        raise AppError("invalid_stage_checkpoint",400)
    root=_checkpoints(project)/name
    if root.is_symlink() or not root.is_dir():
        raise AppError("unknown_stage_checkpoint",404)
    meta=root/"manifest.json"
    if meta.is_symlink() or not meta.is_file() or meta.stat().st_size>8192:
        raise AppError("invalid_stage_checkpoint_manifest",403)
    try: doc=json.loads(meta.read_text())
    except (OSError,ValueError):
        raise AppError("invalid_stage_checkpoint_manifest",403)
    paths=_volumes(project,manifest)
    if (doc.get("version") not in (1,2,3,4) or doc.get("id")!=name or
            doc.get("volumes")!=[rel for rel,_ in paths]):
        raise AppError("stage_checkpoint_volume_mismatch",403)
    result=[]
    for rel,dst in paths:
        source=root/"volumes"/rel
        if source.is_symlink() or not source.is_dir():
            raise AppError("stage_checkpoint_data_missing",403)
        _scan(source,[0,0])
        if doc["version"]>=2:
            stored=doc.get("integrity")
            if (not isinstance(stored,dict)
                    or set(stored)!={rel for rel,_ in paths}
                    or stored.get(rel)!=_digest_tree(source)):
                raise AppError("stage_checkpoint_integrity_mismatch",409)
        result.append((source,dst))
    if doc["version"]>=3:
        observed=sum(_sqlite_check(src) for src,_ in result)
        if type(doc.get("sqlite_files_verified")) is not int or observed!=doc["sqlite_files_verified"]:
            raise AppError("stage_sqlite_checkpoint_mismatch",409)
    if is_qui_pg(manifest):
        if doc.get("version")!=4 or doc.get("postgresql_cold_verified") is not True:
            raise AppError("stage_postgres_checkpoint_evidence_missing",409)
        verify_pg_cold(project,manifest,
                       root/"volumes"/"postgres"/"volume-0",ROOT)
    return result

def _apply(project,manifest,name):
    sources=_validate_snapshot(project,manifest,name)
    # Preflight BOTH current contents and archived contents before modifying.
    # A restore has TWO separate datasets of which only one must fit
    # the per-checkpoint quota: source archive and current destination.
    # Sharing a counter here double-charged a valid 67MB PostgreSQL archive
    # plus its existing 67MB live data against the 128MB snapshot limit.
    source_quota=[0,0]
    destination_quota=[0,0]
    for src,dst in sources:
        _scan(src,source_quota)
        _scan(dst,destination_quota)
    for src,dst in sources:
        # Keep the original bind-root inode/directory in place at all times.
        # This lets the Docker provenance validator work after worker crash.
        for item in dst.iterdir():
            if item.is_dir() and not item.is_symlink():shutil.rmtree(item)
            else:item.unlink()
        for item in src.iterdir():
            target=dst/item.name
            if item.is_dir():_safe_copy(item,target)
            else:
                shutil.copy2(item,target)
        # Container is forced to 1000:1000; restored staging files are writable.
        for current,dirs,files in os.walk(dst):
            for name in files:
                os.chown(Path(current)/name,1000,1000)
            for name in dirs:
                os.chown(Path(current)/name,1000,1000)
        os.chown(dst,1000,1000)
        _sync(dst)
    # A failed post-restore check leaves the durable undo journal in place.
    checked=0
    for src,dst in sources:
        if _digest_tree(src)!=_digest_tree(dst):
            raise AppError("stage_restore_content_mismatch",503)
        checked+=_sqlite_check(dst)
    verify_pg_cold(project,manifest,_dir(project)/"postgres"/"volume-0",ROOT)
    return checked

def restore(project,manifest,services,name):
    _stopped(services)
    pending=_dir(project)/"data-restore-pending.json"
    if pending.exists() or pending.is_symlink():
        raise AppError("stage_data_recovery_required",409)
    _validate_snapshot(project,manifest,name)
    undo=_save(project,manifest)
    _write(pending,{"version":1,"operation":"restore","undo":undo,"target":name})
    try:checked=_apply(project,manifest,name)
    except Exception as e:
        raise AppError("stage_data_restore_requires_recovery",503) from e
    pending.unlink();_sync(_dir(project))
    return {"operation":"restored","checkpoint":name,"undo":undo,
            "sqlite_quick_check_passed":True,"sqlite_files_verified":checked,
            "postgresql_cold_verified":is_qui_pg(manifest),
            "production_mutation_allowed":False,"database_integrity_verified":False}

def recover(project,manifest,services):
    _stopped(services)
    pending=_dir(project)/"data-restore-pending.json"
    if pending.is_symlink() or not pending.is_file():
        raise AppError("no_pending_stage_data_restore",404)
    try:doc=json.loads(pending.read_text())
    except (OSError,ValueError):
        raise AppError("invalid_stage_data_journal",503)
    if not isinstance(doc,dict) or doc.get("version")!=1 or doc.get("operation")!="restore":
        raise AppError("invalid_stage_data_journal",503)
    checked=_apply(project,manifest,doc.get("undo"))
    pending.unlink();_sync(_dir(project))
    return {"operation":"recovered_pre_restore_data",
            "sqlite_quick_check_passed":True,"sqlite_files_verified":checked,
            "production_mutation_allowed":False,"database_integrity_verified":False}
