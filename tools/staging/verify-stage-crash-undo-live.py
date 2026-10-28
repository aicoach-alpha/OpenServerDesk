#!/usr/bin/env python3
"""LIVE stage-only crash journal recovery and checkpoint deletion acceptance."""
import json,secrets,shutil,subprocess
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError

BASE='http://127.0.0.1:18690'
ROOT=Path('/home/andre/projects/openserverdesk/operations/runtime-stage/stage-app-manager')
TOKEN=(ROOT/'token').read_text().strip()


def ids():
    return set(subprocess.check_output(['docker','ps','-a','-q','--no-trunc'],text=True).splitlines())


def api(path, body=None):
    headers={'Authorization':'Bearer '+TOKEN,'Origin':BASE}
    if body is not None:headers['Content-Type']='application/json'
    req=Request(BASE+path,method='POST' if body is not None else 'GET',
                data=json.dumps(body).encode() if body is not None else None,
                headers=headers)
    try:
        with urlopen(req,timeout=20) as r:return r.status,json.load(r)
    except HTTPError as e:return e.code,json.load(e)


def main():
    before=ids()
    name='stage-crash-'+secrets.token_hex(5)+'.txt'
    app=None
    backup=None
    journal=ROOT/'recovery/pending'
    try:
        assert api('/api/v1/stage/files',{'action':'create','name':name,'content':'ORIGINAL'})[0]==200
        status,result=api('/api/v1/stage/apps',{'action':'install'})
        assert status==200
        app=result['app']['name']
        status,result=api('/api/v1/stage/recovery',{'action':'checkpoint'})
        assert status==200
        backup=result['checkpoint']
        assert api('/api/v1/stage/files',{'action':'delete','name':name})[0]==200
        assert api('/api/v1/stage/files',{'action':'create','name':name,'content':'CORRUPTED'})[0]==200
        # Simulate a service crash with a committed, checksummed undo journal.
        # Only this user-owned STAGING recovery folder is modified here.
        shutil.copytree(ROOT/'recovery'/backup,journal,symlinks=True)
        assert api('/api/v1/stage/apps')[0]==409, 'stage action not blocked with pending undo'
        status,result=api('/api/v1/stage/recovery',{'action':'recover'})
        assert status==200,(status,result)
        assert api('/api/v1/stage/files?name='+name)[1]['content']=='ORIGINAL'
        assert api('/api/v1/stage/apps')[1]['apps'][0]['running']
        assert not journal.exists()
        status,result=api('/api/v1/stage/recovery',{'action':'delete','checkpoint':backup})
        assert status==200,(status,result)
        backup=None
        print('LIVE_INTERRUPTED_STAGE_RECOVERY_JOURNAL_ROLLBACK_PASS')
        print('BLOCKED_UNSAFE_STAGE_APP_ACTIONS_UNTIL_UNDO_RESOLVED_PASS')
        print('LIVE_STAGE_CHECKPOINT_DELETE_PASS')
    finally:
        if journal.is_dir() and not journal.is_symlink():
            api('/api/v1/stage/recovery',{'action':'recover'})
        if app:api('/api/v1/stage/apps',{'action':'uninstall','name':app})
        api('/api/v1/stage/files',{'action':'delete','name':name})
        if backup:api('/api/v1/stage/recovery',{'action':'delete','checkpoint':backup})
        assert ids()==before
        print('PRODUCTION_DOCKER_CONTAINER_SET_UNCHANGED',len(before))


if __name__=='__main__':main()
