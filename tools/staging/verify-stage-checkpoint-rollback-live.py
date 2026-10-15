#!/usr/bin/env python3
"""One actual LIVE staged app + storage checkpoint corruption and rollback."""
import json
import secrets
import subprocess
import shutil
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError

BASE='http://127.0.0.1:18690'
root=Path('/opt/openserverdesk-dev/runtime-stage/stage-app-manager')
token=(root/'token').read_text().strip()


def ids():
    return set(subprocess.check_output(
        ['docker','ps','-a','-q','--no-trunc'],text=True).splitlines())


def api(path,method='GET',body=None):
    h={'Authorization':'Bearer '+token,'Origin':'http://127.0.0.1:18690'}
    if body is not None:h['Content-Type']='application/json'
    request=Request(BASE+path,method=method,headers=h,
                    data=json.dumps(body).encode() if body is not None else None)
    try:
        with urlopen(request,timeout=22) as r:return r.status,json.load(r)
    except HTTPError as e:return e.code,json.load(e)


def main():
    original=ids()
    name='stage-restore-'+secrets.token_hex(5)+'.txt'
    after='stage-corrupt-'+secrets.token_hex(5)+'.txt'
    fixture=secrets.token_hex(12)
    app_name=None
    backup=None
    try:
        assert api('/api/v1/stage/files','POST',
                   {'action':'create','name':name,'content':fixture})[0]==200
        status,app=api('/api/v1/stage/apps','POST',{'action':'install'})
        assert status==200,(status,app)
        app_name=app['app']['name']
        assert subprocess.check_output(['docker','exec',app_name,
             'cat','/stage/files/'+name],text=True,timeout=15)==fixture
        status,b=api('/api/v1/stage/recovery','POST',{'action':'checkpoint'})
        assert status==200,(status,b)
        backup=b['checkpoint']
        assert backup.startswith('backup-')
        assert api('/api/v1/stage/files','POST',{'action':'delete','name':name})[0]==200
        assert api('/api/v1/stage/files','POST',
                   {'action':'create','name':after,'content':'broken'})[0]==200
        assert api('/api/v1/stage/files?name='+name)[0]==404
        status,r=api('/api/v1/stage/recovery','POST',
                     {'action':'restore','checkpoint':backup})
        assert status==200,(status,r)
        assert api('/api/v1/stage/files?name='+name)[1]['content']==fixture
        assert api('/api/v1/stage/files?name='+after)[0]==404
        assert api('/api/v1/stage/apps')[1]['apps'][0]['running'] is True
        assert subprocess.check_output(['docker','exec',app_name,
             'cat','/stage/files/'+name],text=True,timeout=15)==fixture
        assert not (root/'recovery/pending').exists()
        print('LIVE_STAGE_CHECKPOINT_CORRUPT_RESTORE_AND_DOCKER_REACTIVATION_PASS')
        print('STAGED_PREEXISTING_DATA_RESTORED_AND_NEW_CORRUPT_FILE_REMOVED_PASS')
    finally:
        if app_name:
            api('/api/v1/stage/apps','POST',
                {'action':'uninstall','name':app_name})
        for f in (name,after):
            api('/api/v1/stage/files','POST',
                {'action':'delete','name':f})
        if backup:
            d=root/'recovery'/backup
            if backup.startswith('backup-') and d.parent==root/'recovery' and not d.is_symlink():
                shutil.rmtree(d)
        assert ids()==original, 'Existing Docker container set changed'
        print('EXISTING_16_DOCKER_CONTAINERS_PRESERVED_PASS')


if __name__=='__main__':main()
