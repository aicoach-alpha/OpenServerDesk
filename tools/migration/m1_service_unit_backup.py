#!/usr/bin/env python3
"""Immutable root-private snapshot of the six existing CasaOS systemd services.

Copies exact active unit and drop-in file bytes/metadata; NEVER edits,
disables, stops or restarts services. Recovery rehearsal to isolated staging.
This is one prerequisite to in-place cutover, not a complete rollback engine.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

NAMES = (
    'casaos.service','casaos-gateway.service','casaos-user-service.service',
    'casaos-app-management.service','casaos-local-storage.service',
    'casaos-message-bus.service',
)
BASE = Path('/var/backups/openserverdesk-migration')
STAGING = Path('/home/andre/projects/openserverdesk/operations/runtime-stage')
MANIFEST='unit-manifest.json'


class SnapshotError(RuntimeError):
    pass


def command(*args):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=12)
    except (OSError,subprocess.TimeoutExpired):
        raise SnapshotError('systemctl query failed')
    if p.returncode:raise SnapshotError('systemctl query unavailable')
    return p.stdout.strip()


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def supported(path):
    p=Path(path)
    if (not p.is_absolute() or '..' in p.parts or p.is_symlink()
            or not p.is_file() or p.stat().st_size > 2_000_000
            or not any(p.is_relative_to(prefix) for prefix in
                       (Path('/etc/systemd/system'),Path('/lib/systemd/system'),
                        Path('/usr/lib/systemd/system')))):
        raise SnapshotError('unrecognized or unsafe production unit file')
    return p


def inventory():
    result={}
    for service in NAMES:
        status=command('systemctl','is-active',service)
        if status!='active':
            raise SnapshotError('CasaOS service not healthy')
        original=command('systemctl','show',service,'-p','FragmentPath','--value')
        dropin=command('systemctl','show',service,'-p','DropInPaths','--value')
        paths=[supported(original)]
        paths.extend(supported(x) for x in dropin.split() if x)
        result[service]={
            'state':status,'files':sorted(set(str(p) for p in paths))
        }
    return result


def sync(folder):
    fd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def snapshot():
    if os.geteuid()!=0:raise SnapshotError('root required')
    if not BASE.is_dir() or BASE.is_symlink():raise SnapshotError('unsafe backup base')
    report=inventory()
    preparing=Path(tempfile.mkdtemp(prefix='.unit-backup-',dir=BASE))
    os.chmod(preparing,0o700)
    name='casaos-units-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'Z'
    if (BASE/name).exists():raise SnapshotError('unit backup name already present')
    try:
        files={}
        for service,details in report.items():
            for path in details['files']:
                if path in files:continue
                src=supported(path)
                st=src.stat()
                old_hash=sha(src)
                dest=preparing/'data'/path.lstrip('/')
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(src,dest)
                os.chown(dest,st.st_uid,st.st_gid)
                os.chmod(dest,stat.S_IMODE(st.st_mode))
                if sha(src)!=old_hash or sha(dest)!=old_hash:
                    raise SnapshotError('production unit changed during snapshot')
                if stat.S_IMODE(dest.stat().st_mode)!=stat.S_IMODE(st.st_mode):
                    raise SnapshotError('unit metadata mismatch')
                files[path]={
                    'sha256':old_hash,'bytes':st.st_size,
                    'mode':stat.S_IMODE(st.st_mode),
                    'uid':st.st_uid,'gid':st.st_gid,
                }
        manifest={
            'format':'OSD_CASAOS_UNITS_V1',
            'created_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'services':report,'files':files,
            'production_modified':False,'migration_allowed':False,
        }
        with (preparing/MANIFEST).open('x') as out:
            json.dump(manifest,out,sort_keys=True)
            out.flush();os.fsync(out.fileno())
        sync(preparing)
        os.replace(preparing,BASE/name)
        sync(BASE)
        return {'snapshot':name,
                'services_preserved':len(report),
                'unit_files_preserved':len(files),
                'manifest_sha256':sha(BASE/name/MANIFEST),
                'production_modified':False}
    finally:
        if preparing.exists():shutil.rmtree(preparing)


def verify(name):
    if not name.startswith('casaos-units-') or '/' in name or '..' in name:
        raise SnapshotError('invalid unit snapshot name')
    folder=BASE/name
    if folder.is_symlink() or not folder.is_dir():raise SnapshotError('unsafe unit backup')
    manifest_file=folder/MANIFEST
    if manifest_file.is_symlink() or manifest_file.stat().st_size>100000:
        raise SnapshotError('unsafe unit manifest')
    report=json.loads(manifest_file.read_text())
    if (report.get('format')!='OSD_CASAOS_UNITS_V1'
            or set(report.get('services',{}))!=set(NAMES)
            or report.get('production_modified') is not False):
        raise SnapshotError('invalid unit manifest')
    with tempfile.TemporaryDirectory(prefix='osd-unit-restore-',dir=STAGING) as tmp:
        sandbox=Path(tmp)
        for path,detail in report['files'].items():
            src=folder/'data'/path.lstrip('/')
            if (src.is_symlink() or sha(src)!=detail['sha256']
                    or src.stat().st_size!=detail['bytes']):
                raise SnapshotError('corrupt unit snapshot')
            dest=sandbox/'restore'/path.lstrip('/')
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(src,dest)
            if sha(dest)!=detail['sha256']:
                raise SnapshotError('unit restoration mismatch')
    return {
        'verified_service_units':len(report['services']),
        'verified_unit_files':len(report['files']),
        'isolated_recovery_rehearsal':'pass',
        'production_modified':False,
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('snapshot','verify'))
    parser.add_argument('--name')
    args=parser.parse_args()
    try:
        if args.action=='snapshot':result=snapshot()
        else:result=verify(args.name or '')
        print(json.dumps(result,sort_keys=True))
    except (OSError,ValueError,SnapshotError) as exc:
        print(json.dumps({'status':'blocked','reason':str(exc)[:150],
                          'production_modified':False}),file=sys.stderr)
        raise SystemExit(2)


if __name__=='__main__':
    main()
