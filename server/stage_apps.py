"""Authenticated, strictly staging-owned Docker app lifecycle.

Never operates on legacy CasaOS/other Docker objects. All operations on
this feature require a disk-held capability AND double-check persisted full
container ID and immutable Docker owner labels before *each* action.
"""
from __future__ import annotations
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import subprocess
from contextlib import contextmanager
from pathlib import Path

STAGE = Path('/opt/openserverdesk-dev/runtime-stage/stage-app-manager')
MARKER = Path('/opt/openserverdesk-dev/runtime-stage/.enable-stage-app-manager')
MARKER_TEXT = 'OSD_STAGE_APP_MANAGER_V1\n'
STAGING_IMAGE = 'busybox:latest'
STAGE_STORAGE = STAGE / 'files'
STAGE_CONTAINER_MOUNT = '/stage/files'
ID_RE = re.compile(r'[a-f0-9]{64}\Z')
NAME_RE = re.compile(r'osd-m1-owned-[a-f0-9]{12}\Z')


class AppError(Exception):
    def __init__(self, message, status=409):
        self.message, self.status = message, status
        super().__init__(message)


def enabled():
    try:
        st = MARKER.lstat()
        return (stat.S_ISREG(st.st_mode) and st.st_uid == 0
                and not st.st_mode & 0o022
                and MARKER.read_text() == MARKER_TEXT
                and STAGE.is_dir() and not STAGE.is_symlink()
                and STAGE_STORAGE.is_dir() and not STAGE_STORAGE.is_symlink())
    except OSError:
        return False


def authenticate(header):
    if not enabled():
        raise AppError('stage_application_manager_disabled', 503)
    if not isinstance(header, str) or not header.startswith('Bearer '):
        raise AppError('authentication_required', 401)
    supplied = header[7:]
    if not re.fullmatch('[0-9a-f]{64}', supplied):
        raise AppError('invalid_stage_credential', 401)
    file = STAGE / 'token'
    try:
        st = file.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o077:
            raise ValueError('unsafe token permissions')
        secret = file.read_text().strip()
    except (OSError, ValueError):
        raise AppError('stage_credential_unavailable', 503)
    if not hmac.compare_digest(supplied, secret):
        raise AppError('invalid_stage_credential', 401)


def docker(*args, max_output=500000):
    # A fixed CLI prefix: no shell interpolation or caller-controlled flags.
    try:
        p = subprocess.run(['docker', *args], capture_output=True,
                           timeout=25, check=False)
        if p.returncode or len(p.stdout) > max_output:
            raise AppError('stage_docker_action_failed', 503)
        return p.stdout.decode('utf-8', 'strict').strip()
    except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError):
        raise AppError('stage_docker_unavailable', 503)


def registry():
    f = STAGE / 'registry.json'
    if f.is_symlink() or not f.is_file():
        raise AppError('stage_registry_unavailable', 503)
    try:
        data = json.loads(f.read_text())
        if (not isinstance(data, dict) or set(data) != {'owner', 'apps'}
                or not re.fullmatch('[a-f0-9]{32}', data['owner'])
                or not isinstance(data['apps'], dict) or len(data['apps']) > 40):
            raise ValueError('bad registry')
        for name, ident in data['apps'].items():
            if not NAME_RE.fullmatch(name) or not ID_RE.fullmatch(ident):
                raise ValueError('bad app ID')
        return data
    except (OSError, ValueError, TypeError):
        raise AppError('stage_registry_corrupt', 503)


def persist(data):
    f = STAGE / 'registry.json'
    temp = STAGE / ('.registry.' + secrets.token_hex(10))
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, f)
        parent = os.open(STAGE, os.O_DIRECTORY | os.O_RDONLY)
        try: os.fsync(parent)
        finally: os.close(parent)
    finally:
        temp.unlink(missing_ok=True)


@contextmanager
def guarded(allow_pending=False):
    if not enabled():
        raise AppError('stage_application_manager_disabled', 503)
    lock = STAGE / '.ops.lock'
    if lock.is_symlink():
        raise AppError('unsafe_stage_lock', 503)
    with lock.open('a+') as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AppError('stage_action_in_progress', 409)
        if not allow_pending and (STAGE / 'recovery' / 'pending').exists():
            raise AppError('stage_undo_pending_use_recovery_first',409)
        yield


def inspect_owned(name, ident, owner):
    if not NAME_RE.fullmatch(name) or not ID_RE.fullmatch(ident):
        raise AppError('invalid_owned_app_identity', 403)
    try:
        obj = json.loads(docker('inspect', '--type', 'container', ident))[0]
    except (ValueError, KeyError, IndexError, TypeError):
        raise AppError('stage_app_inspection_failed', 503)
    if obj.get('Id') != ident or obj.get('Name') != '/' + name:
        raise AppError('stage_app_identity_changed', 403)
    cfg = obj.get('Config') or {}
    host = obj.get('HostConfig') or {}
    labels = cfg.get('Labels') or {}
    mounts = obj.get('Mounts') or []
    # This is the ONLY allowed bind: strictly stage-owned text files mounted
    # read-only, never a production source or Docker daemon socket.
    storage_mount_ok = (len(mounts) == 1
                        and mounts[0].get('Type') == 'bind'
                        and mounts[0].get('Source') == str(STAGE_STORAGE)
                        and mounts[0].get('Destination') == STAGE_CONTAINER_MOUNT
                        and mounts[0].get('RW') is False)
    if (labels.get('osd.m1.managed') != 'stage-only'
            or labels.get('osd.m1.owner') != owner
            or labels.get('osd.m1.storage') != 'stage-files-v1'
            or cfg.get('Image') != STAGING_IMAGE
            or cfg.get('User') != '1000:1000'
            or host.get('Privileged') is not False
            or host.get('NetworkMode') != 'none'
            or host.get('PortBindings')
            or not storage_mount_ok
            or host.get('Binds')):
        raise AppError('container_is_not_owned_isolated_stage_app', 403)
    state = obj.get('State') or {}
    return {'id': ident[:12], 'name': name,
            'image': cfg.get('Image'), 'running': bool(state.get('Running', False)),
            'state': str(state.get('Status', 'unknown'))[:60],
            'isolated': True}


def list_apps():
    with guarded():
        reg = registry()
        return {'scope': 'isolated_stage_owned_apps_only',
                'apps': [inspect_owned(name, ident, reg['owner'])
                         for name, ident in sorted(reg['apps'].items())],
                'production_mutation_allowed': False}


def action(op, name=None):
    if op not in ('install', 'start', 'stop', 'restart', 'uninstall'):
        raise AppError('unsupported_stage_operation', 400)
    with guarded():
        reg = registry()
        if op == 'install':
            if name is not None:
                raise AppError('app_identifier_not_valid_for_install', 400)
            if len(reg['apps']) >= 8:
                raise AppError('staging_app_capacity_reached', 409)
            name = 'osd-m1-owned-' + secrets.token_hex(6)
            ident = docker('run', '--detach', '--pull', 'never',
                           '--name', name,
                           '--label', 'osd.m1.managed=stage-only',
                           '--label', 'osd.m1.owner=' + reg['owner'],
                           '--label', 'osd.m1.storage=stage-files-v1',
                           '--mount', 'type=bind,src=' + str(STAGE_STORAGE)
                                      + ',dst=' + STAGE_CONTAINER_MOUNT + ',readonly',
                           '--network', 'none', '--read-only',
                           '--user', '1000:1000',
                           '--cap-drop', 'ALL',
                           '--security-opt', 'no-new-privileges',
                           '--memory', '64m', '--pids-limit', '32',
                           '--restart', 'no',
                           '--entrypoint', 'sleep', STAGING_IMAGE, '86400')
            if not ID_RE.fullmatch(ident):
                raise AppError('unexpected_docker_create_result', 503)
            # If publication fails, fail closed and NEVER mutate unknown objects.
            try:
                inspect_owned(name, ident, reg['owner'])
                reg['apps'][name] = ident
                persist(reg)
            except Exception:
                # Only remove the just-created exact full ID, and only when
                # its owner labels match; never touch any prior Docker object.
                try: inspect_owned(name, ident, reg['owner'])
                except AppError: pass
                else: docker('rm', '--force', ident)
                raise
            return {'operation': 'installed', 'app': inspect_owned(name, ident, reg['owner'])}
        if not isinstance(name, str) or name not in reg['apps']:
            raise AppError('unknown_stage_app', 404)
        ident = reg['apps'][name]
        old = inspect_owned(name, ident, reg['owner'])
        if op == 'start' and old['running']:
            raise AppError('stage_app_already_running', 409)
        if op == 'stop' and not old['running']:
            raise AppError('stage_app_already_stopped', 409)
        if op == 'restart' and not old['running']:
            raise AppError('stage_app_not_running', 409)
        if op == 'start': docker('start', ident)
        elif op == 'stop': docker('stop', '--time', '2', ident)
        elif op == 'restart': docker('restart', '--time', '2', ident)
        else:
            docker('rm', '--force', ident)
            reg['apps'].pop(name)
            persist(reg)
            return {'operation': 'uninstalled', 'name': name,
                    'production_mutation_allowed': False}
        return {'operation': op, 'app': inspect_owned(name, ident, reg['owner']),
                'production_mutation_allowed': False}
