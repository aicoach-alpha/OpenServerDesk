#!/usr/bin/env python3
"""Real in-place STAGING-only packaged API activation with automatic rollback.

Changes only openserverdesk-staging.service's override, never CasaOS services.
The full .deb payload is verified before activation and the old unit ExecStart
is restored on any failed validation or interrupted activation. Requires sudo,
exact binary integrity and an explicitly healthy preexisting staging unit.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

PKG = Path('/home/andre/projects/openserverdesk/operations/build/openserverdesk-m1-candidate_0.6.7_amd64.deb')
EXPECTED_SHA = '48ce44ede018f7b2192700b753bc1190dcf337bf2bcc462448b66f4884c80531'
RELEASE_BASE = Path('/home/andre/projects/openserverdesk/operations/releases')
DEPLOY = RELEASE_BASE / '0.6.7'
DROPIN = Path('/etc/systemd/system/openserverdesk-staging.service.d/30-osd-package-activation.conf')
RECEIPT = RELEASE_BASE / 'openserverdesk-staging-v0.6.7-receipt.json'
STAGE_UNIT = 'openserverdesk-staging.service'
ORIGINAL_CMD = '/home/andre/projects/openserverdesk/main/server/app.py'
PORT = 'http://127.0.0.1:18690'


class DeploymentError(RuntimeError):
    pass


def check(*args, timeout=25):
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise DeploymentError('deployment action failed: ' + args[0])
    return r.stdout.strip()


def fingerprint(path):
    h=hashlib.sha256()
    with path.open('rb') as file:
        for buf in iter(lambda: file.read(1024*1024), b''):
            h.update(buf)
    return h.hexdigest()


def live(path, *, optional=False):
    try:
        with urlopen(PORT + path, timeout=3) as result:
            if result.status != 200:
                raise DeploymentError('staging health status invalid')
            return json.load(result) if path != '/ui' else result.read(64000).decode()
    except (OSError, ValueError):
        if optional:
            return None
        raise DeploymentError('staging health endpoint missing: '+path)


def probe():
    health=live('/health')
    if health.get('service')!='openserverdesk' or health.get('environment')!='staging':
        raise DeploymentError('unexpected staging service response')
    ui=live('/ui')
    if 'OpenServerDesk' not in ui or 'stage-token' not in ui:
        raise DeploymentError('packaged M1 stage UI incomplete')
    docker=live('/api/v1/docker/containers')
    if docker.get('source')!='local_docker_engine_read_only' or docker.get('container_count',0)<1:
        raise DeploymentError('staging Docker integration unavailable')
    coverage=live('/api/v1/migration/data-coverage')
    if coverage.get('production_modified') is not False:
        raise DeploymentError('unexpected migration coverage response')
    readiness=live('/api/v1/migration/readiness')
    if readiness.get('migration_allowed') is not False:
        raise DeploymentError('production migration flag changed')
    services={
        name: check('systemctl','is-active',name)
        for name in (
            'casaos.service','casaos-gateway.service','casaos-user-service.service',
            'casaos-app-management.service','casaos-local-storage.service',
            'casaos-message-bus.service',
        )
    }
    if set(services.values())!={'active'}:
        raise DeploymentError('production services not healthy')
    return {'health':'pass','ui':'pass','docker_count':docker['container_count'],
            'readiness_migration_allowed':False,'casaos_services':services}


def restart():
    check('systemctl','daemon-reload')
    check('systemctl','restart',STAGE_UNIT,timeout=25)
    for _ in range(25):
        try:return probe()
        except DeploymentError:time.sleep(0.2)
    raise DeploymentError('staging service failed post-activation checks')


def _safe_write(content):
    if DROPIN.is_symlink() or DROPIN.exists():
        raise DeploymentError('staging override already exists; refusing overwrite')
    if DROPIN.parent.is_symlink() or not DROPIN.parent.is_dir():
        raise DeploymentError('staging dropin directory unavailable')
    fd,temp=tempfile.mkstemp(prefix='.osd-stage-release-',dir=DROPIN.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            stream.write(content)
            stream.flush(); os.fsync(stream.fileno())
        os.chmod(temp,0o644)
        os.replace(temp,DROPIN)
    finally:Path(temp).unlink(missing_ok=True)


def activate():
    if os.geteuid()!=0:
        raise DeploymentError('root authorization required')
    if fingerprint(PKG)!=EXPECTED_SHA:
        raise DeploymentError('candidate package integrity mismatch')
    if check('dpkg-deb','--field',str(PKG),'Version')!='0.6.7':
        raise DeploymentError('wrong candidate package version')
    if not RELEASE_BASE.is_dir() or RELEASE_BASE.is_symlink():
        raise DeploymentError('release directory not provisioned')
    if DEPLOY.exists() or DROPIN.exists() or DROPIN.is_symlink() or RECEIPT.exists():
        raise DeploymentError('existing activation; refusing repeat')
    current=check('systemctl','show',STAGE_UNIT,'-p','ExecStart','--value')
    if ORIGINAL_CMD not in current:
        raise DeploymentError('unexpected existing staging unit ExecStart')
    old=probe()
    preparing=Path(tempfile.mkdtemp(prefix='.osd-stage-unpack-',dir=RELEASE_BASE))
    try:
        check('dpkg-deb','--extract',str(PKG),str(preparing),timeout=90)
        script=preparing/'usr/lib/openserverdesk/server/app.py'
        required=['readiness.py','docker_readonly.py','stage_apps.py',
                  'stage_storage.py','stage_recovery.py','ui/index.html',
                  'ui/app.js','ui/style.css']
        if not script.is_file() or any(not (script.parent/x).is_file() for x in required):
            raise DeploymentError('packaged API or UI incomplete')
        expected_entry=('/usr/bin/python3 -B '+
            str(DEPLOY/'usr/lib/openserverdesk/server/app.py'))
        # mkdtemp defaults to mode 0700; the systemd stage service runs as
        # unprivileged andre and MUST be able to traverse the published root.
        # Only publish package data after retaining root ownership and
        # explicit directory traversal, not writable permissions.
        os.chmod(preparing, 0o755)
        # Publication is isolated; never install deb maintainer scripts.
        os.replace(preparing, DEPLOY)
        _safe_write('[Service]\nExecStart=\nExecStart='+expected_entry+'\n')
        try:
            after=restart()
        except Exception:
            # Staging-only rollback to the original known-good Git checkout.
            DROPIN.unlink(missing_ok=True)
            restart()
            raise
        with RECEIPT.open('x') as output:
            json.dump({
                'release':'0.6.7','sha256':EXPECTED_SHA,
                'previous_entrypoint':ORIGINAL_CMD,'new_entrypoint':expected_entry,
                'activated_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                'preflight':old,'postflight':after,'casaos_production_changed':False,
                'migration_allowed':False,
            },output,indent=2,sort_keys=True)
            output.flush();os.fsync(output.fileno())
        return after
    finally:
        if preparing.exists():shutil.rmtree(preparing)


def rollback():
    if os.geteuid()!=0:raise DeploymentError('root required')
    if not DROPIN.is_file() or DROPIN.is_symlink():
        raise DeploymentError('expected stage override is absent')
    expected = 'ExecStart=/usr/bin/python3 -B '+str(
        DEPLOY/'usr/lib/openserverdesk/server/app.py')
    if expected not in DROPIN.read_text():
        raise DeploymentError('unrecognized stage override; stop')
    DROPIN.unlink()
    status=restart()
    return status


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['activate','rollback','status'])
    args=parser.parse_args()
    try:
        if args.action=='activate': result=activate()
        elif args.action=='rollback':result=rollback()
        else:result=probe()
        print(json.dumps({'status':'pass','mode':'packaged_staging_only',
                          'result':result,'migration_allowed':False,
                          'production_modified':False},sort_keys=True))
    except (DeploymentError,OSError,ValueError,subprocess.TimeoutExpired) as err:
        print(json.dumps({'status':'failed','reason':str(err)[:180],
                          'production_modified':False},sort_keys=True))
        raise SystemExit(2)


if __name__=='__main__':main()
