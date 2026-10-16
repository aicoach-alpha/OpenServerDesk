"""Authenticated, transactional stage-only application file recovery.

Only manages the local, private stage file store and stage-owned isolated
containers; never references production volumes or workloads. Each restore
has a durable, checksummed undo journal and fail-closed crash recovery.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import tempfile
from pathlib import Path
from stage_apps import STAGE, AppError, guarded, registry, inspect_owned, docker
from stage_storage import ROOT as FILES, NAME, MAX_FILE

RECOVERY = STAGE / 'recovery'
BACKUP_NAME = re.compile('backup-[0-9a-f]{12}\\Z')
MAX_BACKUPS = 5


def _reject_partial_compose_recovery():
    # Legacy stage-file checkpoints cannot claim to restore a newly added
    # Compose project. Use dedicated Compose checkpoint/recovery instead.
    from stage_compose import _registry as compose_registry
    if compose_registry():
        raise AppError("compose_projects_require_separate_checkpoint", 409)


def checksum(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(65536),b''):
            h.update(chunk)
    return h.hexdigest()


def syncdir(path):
    fd=os.open(path,os.O_DIRECTORY | os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def _files_index(path):
    if path.is_symlink() or not path.is_dir():
        raise AppError('unsafe_stage_data_directory',503)
    rows={}
    entries=list(path.iterdir())
    if len(entries)>500:
        raise AppError('stage_file_capacity_limit',409)
    for file in sorted(entries):
        st=file.lstat()
        if (not NAME.fullmatch(file.name)
                or not stat.S_ISREG(st.st_mode)
                or st.st_nlink!=1 or st.st_size>MAX_FILE):
            raise AppError('unsupported_stage_file_entry',403)
        rows[file.name]={'sha256':checksum(file),'bytes':st.st_size}
    return rows


def _copy_verified(src,dst,index):
    dst.mkdir(mode=0o700)
    for name,expected in sorted(index.items()):
        if not NAME.fullmatch(name):
            raise AppError('unsafe_backup_file_name',403)
        source=src/name
        st=source.lstat()
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink!=1
                or checksum(source)!=expected['sha256']):
            raise AppError('source_changed_during_stage_copy',409)
        out=dst/name
        fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            with os.fdopen(fd,'wb') as handle, source.open('rb') as inp:
                shutil.copyfileobj(inp,handle)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            out.unlink(missing_ok=True)
            raise
    if _files_index(dst)!=index:
        raise AppError('recovered_stage_data_hash_mismatch',409)
    syncdir(dst)


def _write_manifest(folder,manifest):
    path=folder/'manifest.json'
    with path.open('x') as stream:
        json.dump(manifest,stream,sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    syncdir(folder)


def _read_bundle(folder,expected_owner):
    if folder.is_symlink() or not folder.is_dir():
        raise AppError('stage_backup_unavailable',404)
    doc=folder/'manifest.json'
    try:
        if doc.is_symlink() or not doc.is_file() or doc.stat().st_size>100000:
            raise AppError('unsafe_stage_backup_manifest',403)
    except OSError:
        raise AppError('stage_backup_manifest_unavailable',503)
    try:raw=json.loads(doc.read_text())
    except (ValueError,OSError):raise AppError('invalid_stage_backup_manifest',409)
    if (not isinstance(raw,dict)
            or set(raw)!={'format','owner','files','apps'}
            or raw['format']!=1 or raw['owner']!=expected_owner
            or not isinstance(raw['files'],dict)
            or not isinstance(raw['apps'],dict)):
        raise AppError('foreign_or_invalid_stage_backup',403)
    if not all(NAME.fullmatch(k) and isinstance(v,dict)
               and set(v)=={'sha256','bytes'} and
               isinstance(v['sha256'],str) and re.fullmatch('[0-9a-f]{64}',v['sha256']) and
               type(v['bytes']) is int and 0<=v['bytes']<=MAX_FILE
               for k,v in raw['files'].items()):
        raise AppError('invalid_stage_backup_entries',403)
    if _files_index(folder/'data')!=raw['files']:
        raise AppError('stage_backup_integrity_failure',409)
    return raw


def _apps_now(reg):
    return {name:inspect_owned(name, ident, reg['owner'])
            for name,ident in sorted(reg['apps'].items())}


def _initialize_root():
    if RECOVERY.is_symlink() or not RECOVERY.is_dir():
        raise AppError('stage_recovery_not_initialized',503)


def _published():
    return sorted(p for p in RECOVERY.iterdir()
                  if BACKUP_NAME.fullmatch(p.name) and p.is_dir() and not p.is_symlink())


def list_backups():
    with guarded():
        _initialize_root()
        reg=registry()
        result=[]
        for folder in _published():
            doc=_read_bundle(folder,reg['owner'])
            result.append({'id':folder.name, 'files':len(doc['files']),
                           'apps':len(doc['apps'])})
        return {'backups':result,'pending_recovery':False,
                'production_mutation_allowed':False}


def checkpoint():
    with guarded():
        _reject_partial_compose_recovery()
        _initialize_root()
        if (RECOVERY/'pending').exists():
            raise AppError('unresolved_stage_recovery_journal',409)
        if len(_published())>=MAX_BACKUPS:
            raise AppError('stage_backup_limit_reached',409)
        reg=registry()
        apps=_apps_now(reg)
        before=_files_index(FILES)
        temp=Path(tempfile.mkdtemp(prefix='.checkpoint-',dir=RECOVERY))
        try:
            _copy_verified(FILES,temp/'data',before)
            if _files_index(FILES)!=before:
                raise AppError('concurrent_stage_file_mutation',409)
            _write_manifest(temp,{
                'format':1,'owner':reg['owner'],'files':before,
                'apps':{name:{'id':reg['apps'][name],
                              'running':app['running']} for name,app in apps.items()},
            })
            name='backup-'+secrets.token_hex(6)
            os.replace(temp,RECOVERY/name)
            syncdir(RECOVERY)
            return {'checkpoint':name,'files':len(before),
                    'apps':len(apps),'production_mutation_allowed':False}
        finally:
            if temp.exists():shutil.rmtree(temp)


def _stop_owned(reg, apps):
    for name,entry in apps.items():
        state=inspect_owned(name,reg['apps'][name],reg['owner'])
        if state['running']:
            docker('stop','--time','2',reg['apps'][name])


def _resume_owned(reg,states):
    for name,entry in states.items():
        current=inspect_owned(name,reg['apps'][name],reg['owner'])
        if entry['running'] and not current['running']:
            docker('start',reg['apps'][name])


def _replace_files(index, source):
    # Recovery and stage local file API share exclusive guarded() lock.
    # Docker writer access to bind mount is explicitly read-only.
    preparing=Path(tempfile.mkdtemp(prefix='.restore-data-',dir=STAGE))
    try:
        _copy_verified(source,preparing/'data',index)
        # Apply files in-place because Docker binds the *directory inode*.
        # An undo journal is published before touching this source.
        existing=_files_index(FILES)
        for name in existing:
            (FILES/name).unlink()
        for name in index:
            os.replace(preparing/'data'/name,FILES/name)
        syncdir(FILES)
        if _files_index(FILES)!=index:
            raise AppError('stage_restore_integrity_failed',409)
    finally:
        if preparing.exists():shutil.rmtree(preparing)


def _undo_from_pending(reg,pending):
    undo=_read_bundle(pending,reg['owner'])
    current=_apps_now(reg)
    if set(current)!=set(undo['apps']):
        raise AppError('stage_app_set_changed_during_restore',409)
    _stop_owned(reg,current)
    _replace_files(undo['files'],pending/'data')
    _resume_owned(reg,undo['apps'])
    shutil.rmtree(pending)
    syncdir(RECOVERY)


def restore(name):
    if not isinstance(name,str) or not BACKUP_NAME.fullmatch(name):
        raise AppError('invalid_stage_checkpoint_name',400)
    with guarded(allow_pending=True):
        _reject_partial_compose_recovery()
        _initialize_root()
        pending=RECOVERY/'pending'
        if pending.exists() or pending.is_symlink():
            raise AppError('manual_stage_recovery_required',409)
        reg=registry()
        backup=_read_bundle(RECOVERY/name,reg['owner'])
        current=_apps_now(reg)
        if (set(backup['apps'])!=set(current)
                or any(backup['apps'][k]['id']!=reg['apps'][k] for k in current)):
            raise AppError('stage_app_set_changed_since_checkpoint',409)
        undo_files=_files_index(FILES)
        preparing=Path(tempfile.mkdtemp(prefix='.undo-preparing-',dir=RECOVERY))
        try:
            _copy_verified(FILES,preparing/'data',undo_files)
            _write_manifest(preparing,{
                'format':1,'owner':reg['owner'],'files':undo_files,
                'apps':{n:{'id':reg['apps'][n],'running':v['running']}
                        for n,v in current.items()},
            })
            os.replace(preparing,pending)
            syncdir(RECOVERY)
        finally:
            if preparing.exists():shutil.rmtree(preparing)
        try:
            _stop_owned(reg,current)
            _replace_files(backup['files'], RECOVERY/name/'data')
            _resume_owned(reg, {n:{'running':x['running']}
                                for n,x in current.items()})
            shutil.rmtree(pending)
            syncdir(RECOVERY)
            return {'restored_checkpoint':name,'files':len(backup['files']),
                    'production_mutation_allowed':False}
        except Exception:
            try:
                _undo_from_pending(reg,pending)
            except Exception as err:
                raise AppError('stage_restore_failed_undo_pending',503) from err
            raise AppError('stage_restore_failed_undo_applied',503)


def recover_interrupted():
    with guarded(allow_pending=True):
        _reject_partial_compose_recovery()
        _initialize_root()
        reg=registry()
        pending=RECOVERY/'pending'
        if pending.is_symlink() or not pending.is_dir():
            raise AppError('no_pending_stage_undo',404)
        _undo_from_pending(reg,pending)
        return {'recovered':'previous_stage_state','production_mutation_allowed':False}



def delete_checkpoint(name):
    if not isinstance(name,str) or not BACKUP_NAME.fullmatch(name):
        raise AppError('invalid_stage_checkpoint_name',400)
    with guarded():
        _initialize_root()
        folder=RECOVERY/name
        if folder.is_symlink() or not folder.is_dir():
            raise AppError('stage_backup_unavailable',404)
        # Scoped deletion: only an explicitly named dedicated stage backup,
        # never the live files, registry, authorization key or production.
        shutil.rmtree(folder)
        syncdir(RECOVERY)
        return {'deleted_checkpoint':name,'production_mutation_allowed':False}
