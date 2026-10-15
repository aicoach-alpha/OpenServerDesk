#!/usr/bin/env python3
"""Authenticate against LIVE staging; lifecycle a real owned isolated app."""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

URL='http://127.0.0.1:18690/api/v1/stage/apps'
TOKEN=Path('/opt/openserverdesk-dev/runtime-stage/stage-app-manager/token').read_text().strip()


def docker_ids():
    return set(subprocess.check_output(['docker','ps','-a','-q','--no-trunc'],text=True).splitlines())


def request(method='GET', payload=None, auth=True, extra=None):
    headers={'Origin':'http://127.0.0.1:18690'}
    if auth:headers['Authorization']='Bearer '+TOKEN
    if payload is not None:
        headers['Content-Type']='application/json'
    if extra:headers.update(extra)
    body=json.dumps(payload).encode() if payload is not None else None
    req=Request(URL,headers=headers,data=body,method=method)
    try:
        with urlopen(req,timeout=20) as r:
            return r.status,json.load(r)
    except HTTPError as err:
        return err.code,json.load(err)


def main():
    baseline=docker_ids()
    try:
        assert request(auth=False)[0]==401
        assert request(extra={'Origin':'http://malicious.example'})[0]==403
        assert request(extra={'Authorization':'Bearer '+'0'*64})[0]==401
        assert request('POST',{'action':'stop','name':'casaos-gateway'})[0]==404
        status, app=request('POST',{'action':'install'})
        assert status==200,(status,app)
        name=app['app']['name']
        assert name.startswith('osd-m1-owned-')
        assert app['app']['running'] is True
        assert len(docker_ids()-baseline)==1
        status, listed=request()
        assert status==200 and len(listed['apps'])==1
        assert listed['apps'][0]['name']==name
        status, stopped=request('POST',{'action':'stop','name':name})
        assert status==200 and stopped['app']['running'] is False,(status,stopped)
        status, started=request('POST',{'action':'start','name':name})
        assert status==200 and started['app']['running'] is True,(status,started)
        status, restarted=request('POST',{'action':'restart','name':name})
        assert status==200 and restarted['app']['running'] is True,(status,restarted)
        status, removed=request('POST',{'action':'uninstall','name':name})
        assert status==200 and removed['operation']=='uninstalled',(status,removed)
        assert request()[1]['apps']==[]
        assert docker_ids()==baseline,'Docker production container IDs changed'
        print('LIVE_AUTHENTICATED_STAGE_APP_DOCKER_INSTALL_STOP_START_RESTART_REMOVE_PASS')
        print('ALL_EXISTING_DOCKER_CONTAINER_IDS_PRESERVED_PASS',len(baseline))
        print('UNAUTHORIZED_FORGED_ORIGIN_AND_PRODUCTION_ID_REJECTED_PASS')
    finally:
        # Fail closed; if the test breaks mid-flight, leave the labeled app
        # registered for deliberate stage-only investigation, not blanket rm.
        pass

if __name__=='__main__':
    main()
