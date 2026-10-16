#!/usr/bin/env python3
"""Journaled real staging-service package upgrade 0.6.31 -> 0.6.32.

Only modifies an exact OpenServerDesk staging systemd override. Persists an
undo journal BEFORE switching binaries; recovers to the previous package
when post-activation health checks fail or the process is interrupted.
Never reads, stops or changes CasaOS production configuration/data.
"""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

BASE=Path('/opt/openserverdesk-dev/releases')
PREVIOUS=BASE/'0.6.31'
NEXT=BASE/'0.6.32'
PACKAGE=Path('/opt/openserverdesk-dev/build/openserverdesk-m1-candidate_0.6.32_amd64.deb')
EXPECTED_SHA='8bfa8cbd4495b185976dbae815d3f8087dd573ed947a4ede6962122ecf5ebe3d'
OVERRIDE=Path('/etc/systemd/system/openserverdesk-staging.service.d/30-osd-package-activation.conf')
JOURNAL=BASE/'upgrade-0.6.32-pending.json'
RECEIPT=BASE/'upgrade-0.6.32-receipt.json'
UNIT='openserverdesk-staging.service'
BASE_URL='http://127.0.0.1:18690'


class UpgradeError(RuntimeError):
    pass


def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def run(*args,timeout=40):
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if p.returncode:raise UpgradeError('system operation failed: '+args[0])
    return p.stdout.strip()


def entry(version):
    return ('[Service]\nExecStart=\nExecStart=/usr/bin/python3 -B '+
            str(BASE/version/'usr/lib/openserverdesk/server/app.py')+'\n')


OLD_ENTRY=entry('0.6.31')
NEW_ENTRY=entry('0.6.32')


def live(path):
    with urlopen(BASE_URL+path,timeout=3) as r:
        if r.status!=200:raise UpgradeError('staging endpoint not healthy')
        return json.load(r) if path!='/ui' else r.read(100000).decode()


def readiness(version):
    with urlopen(BASE_URL+'/health',timeout=3) as r:
        h=json.load(r)
    if h.get('version')!=version or h.get('environment')!='staging':
        raise UpgradeError('stage package reported incorrect release version')
    if 'stage-token' not in live('/ui'):
        raise UpgradeError('stage authenticated UI missing')
    d=live('/api/v1/docker/containers')
    if d.get('source')!='local_docker_engine_read_only' or d.get('container_count',0)<1:
        raise UpgradeError('real Docker inventory unavailable')
    r=live('/api/v1/migration/readiness')
    if r.get('migration_allowed') is not False:
        raise UpgradeError('production migration gate changed')
    try:
        with urlopen(BASE_URL+'/api/v1/stage/apps',timeout=3):
            raise UpgradeError('stage application authentication bypass')
    except HTTPError as err:
        if err.code!=401:raise UpgradeError('stage authentication protection failed')
    try:
        live('/api/v1/stage/whoami')
        raise UpgradeError('new user endpoint exposed without credentials')
    except HTTPError as err:
        if err.code!=401:
            raise UpgradeError('stage actor endpoint missing authentication')
    resource=live('/api/v1/docker/resources')
    if (resource.get('source')!='local_docker_resource_metrics_readonly'
            or resource.get('production_modified') is not False
            or resource.get('external_user_data_inspected') is not False
            or resource.get('migration_allowed') is not False
            or resource.get('container_count')!=d['container_count']
            or len(resource.get('containers',[]))!=d['container_count']):
        raise UpgradeError('sanitized Docker resource metrics not functional')
    progress=live('/api/v1/m1/progress')
    if progress.get('progress_percent') != 49 or len(progress.get('milestones',[]))!=11:
        raise UpgradeError('new release progress acceptance does not match verified proof')
    cutover=live('/api/v1/migration/cutover-plan')
    if (cutover.get('scope')!='CASAOS_PLATFORM_CONFIG_ONLY_NO_USER_DATA_MIGRATION'
            or cutover.get('migration_allowed') is not False
            or cutover.get('production_modified') is not False
            or cutover.get('user_data_content_accessed') is not False
            or cutover.get('external_hdd_backup_required') is not False
            or cutover.get('verified_sqlite_databases',0) < 3
            or cutover.get('verified_config_files',0) < 1000
            or len(cutover.get('pending_gates', [])) != 4):
        raise UpgradeError('packaged config-only cutover readiness report unavailable')
    for protected_path in ('/api/v1/stage/compose', '/api/v1/stage/catalog',
                           '/api/v1/stage/topologies',
                           '/api/v1/stage/topologies/health',
                           '/api/v1/stage/casaos-appstore',
                           '/api/v1/stage/casaos-store-pilot',
                           '/api/v1/stage/store-general',
                           '/api/v1/stage/store-compile'):
        try:
            live(protected_path)
            raise UpgradeError('unauthenticated Compose endpoint accepted')
        except HTTPError as err:
            if err.code != 401:
                raise UpgradeError('staged Compose API protection not enforced')
    try:
        live('/api/v1/stage/compose-backups')
        raise UpgradeError('stage Compose backups unauthenticated')
    except HTTPError as err:
        if err.code!=401:
            raise UpgradeError('Compose recovery missing authentication')
    parity=live('/api/v1/m1/compose-parity')
    if (parity.get('source_config_definitions',0)<1
            or parity.get('general_casaos_compose_parity_proven') is not False
            or parity.get('nextcloud_user_files_opened') is not False
            or parity.get('migration_allowed') is not False):
        raise UpgradeError('real CasaOS compatibility baseline unavailable')
    metrics=live('/api/v1/system/status')
    if (metrics.get('source') != 'local_linux_readonly'
            or metrics.get('external_user_data_disks_inspected') is not False
            or metrics.get('production_modified') is not False
            or metrics.get('cpu_logical_cores',0)<1
            or metrics.get('memory',{}).get('total_bytes',0)<1000000):
        raise UpgradeError('staging NAS monitoring scope invalid')
    history=live('/api/v1/m1/progress/history')
    if history.get('automated_monitoring_enabled') is not False:
        raise UpgradeError('user-disabled monitoring unexpectedly enabled')
    for unit in ('casaos','casaos-gateway','casaos-user-service',
                 'casaos-message-bus','casaos-app-management','casaos-local-storage'):
        if run('systemctl','is-active',unit)!='active':
            raise UpgradeError('production service unhealthy')
    return {'package_version':version,'stage_authenticated':True,
            'docker_count':d['container_count'],'production_modified':False,
            'migration_allowed':False}


def write_atomic(path,content,mode=0o600):
    if path.is_symlink():
        raise UpgradeError('unsafe staging activation path')
    fd,name=tempfile.mkstemp(prefix='.osd-upgrade-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(content)
            f.flush();os.fsync(f.fileno())
        os.chmod(name,mode)
        os.replace(name,path)
    finally:
        Path(name).unlink(missing_ok=True)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def switch(text):
    write_atomic(OVERRIDE,text.encode(),mode=0o644)
    run('systemctl','daemon-reload')
    run('systemctl','restart',UNIT)
    for i in range(15):
        try:
            live('/health')
            return
        except (OSError,ValueError,UpgradeError):
            time.sleep(.2)
    raise UpgradeError('staging did not become healthy')


def validate():
    if os.geteuid()!=0:raise UpgradeError('root operator required')
    if sha256(PACKAGE)!=EXPECTED_SHA:
        raise UpgradeError('untrusted package hash')
    if run('dpkg-deb','--field',str(PACKAGE),'Version')!='0.6.32':
        raise UpgradeError('unexpected package version')
    if not PREVIOUS.is_dir() or PREVIOUS.is_symlink():
        raise UpgradeError('prior package not installed')
    if not OVERRIDE.is_file() or OVERRIDE.is_symlink():
        raise UpgradeError('stage version override missing')
    if OVERRIDE.read_text()!=OLD_ENTRY:
        raise UpgradeError('unexpected stage version, not safe to upgrade')
    current=run('systemctl','show',UNIT,'-p','ExecStart','--value')
    if str(PREVIOUS/'usr/lib/openserverdesk/server/app.py') not in current:
        raise UpgradeError('staging systemd entry does not match prior package')
    if NEXT.exists() or JOURNAL.exists() or RECEIPT.exists():
        raise UpgradeError('pending or existing upgrade must be reconciled first')


def upgrade():
    validate()
    temp=Path(tempfile.mkdtemp(prefix='.pkg-0620-',dir=BASE))
    try:
        run('dpkg-deb','--extract',str(PACKAGE),str(temp),timeout=110)
        expected=temp/'usr/lib/openserverdesk/server/app.py'
        release_version=temp/'usr/lib/openserverdesk/server/release-version.txt'
        if not expected.is_file() or release_version.read_text().strip()!='0.6.32':
            raise UpgradeError('missing package API or release attestation')
        os.chmod(temp,0o755)
        os.replace(temp,NEXT)
        # Durable pre-activation journal allows a later call to recover even
        # if this entire controlling process is SIGKILLed mid-flight.
        write_atomic(JOURNAL,json.dumps({
            'from':'0.6.31','to':'0.6.32','old_entry_sha256':
            hashlib.sha256(OLD_ENTRY.encode()).hexdigest(),'new_sha256':EXPECTED_SHA,
        }).encode())
        try:
            switch(NEW_ENTRY)
            after=readiness('0.6.32')
            write_atomic(RECEIPT,json.dumps({
                'status':'live_staging_pass','after':after,
                'artifact_sha256':EXPECTED_SHA,
                'verified_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
            },sort_keys=True).encode())
            JOURNAL.unlink()
            return after
        except BaseException:
            switch(OLD_ENTRY)
            JOURNAL.unlink(missing_ok=True)
            raise
    finally:
        if temp.exists():shutil.rmtree(temp)


def recover():
    if os.geteuid()!=0:raise UpgradeError('root required')
    if not JOURNAL.is_file() or JOURNAL.is_symlink():
        raise UpgradeError('no interrupted upgrade to recover')
    journal=json.loads(JOURNAL.read_text())
    if (journal.get('old_entry_sha256')!=hashlib.sha256(OLD_ENTRY.encode()).hexdigest()
            or journal.get('new_sha256')!=EXPECTED_SHA):
        raise UpgradeError('unexpected recovery journal')
    if OVERRIDE.read_text() not in (OLD_ENTRY,NEW_ENTRY):
        raise UpgradeError('stage unit changed since upgrade')
    switch(OLD_ENTRY)
    JOURNAL.unlink()
    return {'rolled_back_to':'0.6.31','production_modified':False}


def rollback():
    if os.geteuid()!=0:raise UpgradeError('root required')
    if JOURNAL.exists():raise UpgradeError('pending interrupted upgrade; use recover')
    if not RECEIPT.is_file() or RECEIPT.is_symlink():
        raise UpgradeError('no signed-off staging upgrade receipt')
    if OVERRIDE.read_text()!=NEW_ENTRY:
        raise UpgradeError('unexpected current stage version')
    switch(OLD_ENTRY)
    return {'rolled_back_to':'0.6.31','production_modified':False}


def main():
    if len(sys.argv)!=2 or sys.argv[1] not in ('upgrade','recover','rollback'):
        raise SystemExit('Usage: upgrade-packaged-stage.py upgrade|recover|rollback')
    try:
        if sys.argv[1]=='upgrade':r=upgrade()
        elif sys.argv[1]=='recover':r=recover()
        else:r=rollback()
        print(json.dumps({'result':r,'staging_only':True,'production_modified':False},sort_keys=True))
    except (UpgradeError,OSError,ValueError,TimeoutError,subprocess.TimeoutExpired) as err:
        print(json.dumps({'status':'failed','reason':str(err)[:160],
                          'production_modified':False}))
        raise SystemExit(2)


if __name__=='__main__':main()
