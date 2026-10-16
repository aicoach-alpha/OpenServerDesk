"""Secure, staging-only local document store using directory-fd confinement.

No host filesystem paths, traversal, symlinks, hardlinks, arbitrary chmod,
upload into Docker, or mutation of existing production files are supported.
"""
from __future__ import annotations
import os
import re
import stat
import secrets
from pathlib import Path
from stage_apps import STAGE, AppError, guarded

ROOT = STAGE / 'files'
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z')
MAX_FILE = 65536
LIMIT = 500


def _name(name):
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise AppError('invalid_stage_filename', 400)
    return name


def _dirfd():
    if ROOT.is_symlink() or not ROOT.is_dir():
        raise AppError('stage_storage_unavailable', 503)
    try:
        return os.open(ROOT, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise AppError('stage_storage_unavailable', 503)


def _regular(fd, name):
    try:
        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        raise AppError('stage_file_not_found', 404)
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > MAX_FILE:
        raise AppError('unsafe_stage_file', 403)
    return st


def listing():
    with guarded():
        fd = _dirfd()
        try:
            names = os.listdir(fd)
            if len(names) > LIMIT:
                raise AppError('stage_file_capacity_reached', 409)
            result = []
            for name in sorted(names):
                if not NAME.fullmatch(name): 
                    continue
                try:
                    st = _regular(fd, name)
                except AppError:
                    continue
                result.append({'name': name, 'bytes': st.st_size})
            return {'files': result, 'scope': 'isolated_stage_file_store',
                    'production_mutation_allowed': False}
        finally:
            os.close(fd)


def read(name):
    name = _name(name)
    with guarded():
        fd = _dirfd()
        try:
            _regular(fd, name)
            with os.fdopen(os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd),'rb') as f:
                st = os.fstat(f.fileno())
                if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > MAX_FILE:
                    raise AppError('unsafe_stage_file', 403)
                content = f.read(MAX_FILE+1)
            if len(content) > MAX_FILE:
                raise AppError('stage_file_too_large', 413)
            try:
                data = content.decode('utf-8','strict')
            except UnicodeError:
                raise AppError('non_text_stage_file', 415)
            return {'name':name,'content':data}
        finally:
            os.close(fd)


def perform(action, name, content=None):
    name = _name(name)
    if action not in ('create','delete'):
        raise AppError('invalid_stage_file_operation', 400)
    with guarded():
        fd = _dirfd()
        try:
            if action == 'create':
                if not isinstance(content,str) or len(content.encode('utf-8')) > MAX_FILE:
                    raise AppError('stage_file_content_invalid', 400)
                if len(os.listdir(fd)) >= LIMIT:
                    raise AppError('stage_file_capacity_reached', 409)
                try:
                    file_fd=os.open(name, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,
                                    0o600, dir_fd=fd)
                except FileExistsError:
                    raise AppError('existing_stage_file_must_not_be_overwritten',409)
                with os.fdopen(file_fd,'wb') as f:
                    f.write(content.encode('utf-8'))
                    f.flush()
                    os.fsync(f.fileno())
                os.fsync(fd)
                return {'created':name,'bytes':len(content.encode('utf-8'))}
            _regular(fd,name)
            os.unlink(name,dir_fd=fd)
            os.fsync(fd)
            return {'deleted':name}
        except OSError:
            raise AppError('stage_storage_action_failed', 503)
        finally:
            os.close(fd)


def create_binary(name, content):
    """Create stage-owned binary data, no overwrite, no external paths."""
    name=_name(name)
    if not isinstance(content,bytes) or len(content)>MAX_FILE:
        raise AppError("stage_binary_content_invalid",413)
    with guarded():
        fd=_dirfd()
        try:
            if len(os.listdir(fd))>=LIMIT:
                raise AppError("stage_file_capacity_reached",409)
            try:
                handle=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,
                               0o600,dir_fd=fd)
            except FileExistsError:
                raise AppError("existing_stage_file_must_not_be_overwritten",409)
            with os.fdopen(handle,"wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(fd)
            return {"created":name,"bytes":len(content),
                    "scope":"isolated_stage_file_store"}
        finally:
            os.close(fd)


def download_binary(name):
    """Return verified stage-only file bytes; no path lookup outside dirfd."""
    name=_name(name)
    with guarded():
        fd=_dirfd()
        try:
            _regular(fd,name)
            handle=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
            with os.fdopen(handle,"rb") as stream:
                st=os.fstat(stream.fileno())
                if (not stat.S_ISREG(st.st_mode) or st.st_nlink!=1
                        or st.st_size>MAX_FILE):
                    raise AppError("unsafe_stage_file",403)
                data=stream.read(MAX_FILE+1)
            if len(data)>MAX_FILE:
                raise AppError("unsafe_stage_file",403)
            return data
        finally:
            os.close(fd)
