#!/usr/bin/env python3
"""One real LIVE authenticated stage AppManagement + LocalStorage end-to-end."""
from __future__ import annotations
import json
import secrets
import subprocess
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError

BASE='http://127.0.0.1:18690'
TOKEN=Path('/opt/openserverdesk-dev/runtime-stage/stage-app-manager/token').read_text().strip()


def ids():
    return set(subprocess.check_output(['docker','ps','-a','-q','--no-trunc'],text=True).splitlines())


def api(route, method='GET', payload=None):
    h={'Authorization':'Bearer '+TOKEN, 'Origin':'http://127.0.0.1:18690'}
    data=None
    if payload is not None:
        h['Content-Type']='application/json'
        data=json.dumps(payload).encode()
    req=Request(BASE+route,method=method,headers=h,data=data)
    try:
        with urlopen(req,timeout=15) as r:
            return r.status,json.load(r)
    except HTTPError as error:
        return error.code,json.load(error)


def main():
    baseids=ids()
    name='m1-integrated-'+secrets.token_hex(5)+'.txt'
    content='stage-only persistent data '+secrets.token_hex(8)
    app_name=None
    try:
        status,_=api('/api/v1/stage/files','POST',
                     {'action':'create','name':name,'content':content})
        assert status==200
        status,res=api('/api/v1/stage/apps','POST',{'action':'install'})
        assert status==200,(status,res)
        app_name=res['app']['name']
        assert res['app']['running']
        assert len(ids()-baseids)==1
        read=subprocess.check_output(['docker','exec',app_name,
                                      'cat','/stage/files/'+name],timeout=15,text=True)
        assert read==content,'App container cannot access staged file data'
        status,_=api('/api/v1/stage/apps','POST',{'action':'stop','name':app_name})
        assert status==200
        status,_=api('/api/v1/stage/apps','POST',{'action':'start','name':app_name})
        assert status==200
        status,_=api('/api/v1/stage/apps','POST',{'action':'restart','name':app_name})
        assert status==200
        read=subprocess.check_output(['docker','exec',app_name,
                                      'cat','/stage/files/'+name],timeout=15,text=True)
        assert read==content,'Storage missing after stage app restart'
        # Verify readonly bind within running app cannot be written through.
        p=subprocess.run(['docker','exec',app_name,'sh','-c',
            'echo MUTATED >/stage/files/'+name],capture_output=True,timeout=15)
        assert p.returncode!=0,'Stage app unexpectedly modified storage'
        assert api('/api/v1/stage/files?name='+name)[1]['content']==content
        status,_=api('/api/v1/stage/apps','POST',{'action':'uninstall','name':app_name})
        assert status==200
        app_name=None
        status,_=api('/api/v1/stage/files','POST',{'action':'delete','name':name})
        assert status==200
        assert ids()==baseids,'Existing Docker containers changed'
        print('LIVE_AUTHENTICATED_APPMANAGEMENT_LOCALSTORAGE_INTEGRATION_PASS')
        print('STAGED_STORAGE_PERSISTED_THROUGH_STOP_START_RESTART_PASS')
        print('STAGED_APP_STORAGE_READ_ONLY_ENFORCED_PASS')
        print('PRODUCTION_DOCKER_IDS_PRESERVED_PASS',len(baseids))
    finally:
        if app_name:
            api('/api/v1/stage/apps','POST',{'action':'uninstall','name':app_name})
        api('/api/v1/stage/files','POST',{'action':'delete','name':name})


if __name__=='__main__':
    main()
