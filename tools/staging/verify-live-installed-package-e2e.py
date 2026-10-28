#!/usr/bin/env python3
"""Genuine E2E against installed, running versioned staged package on NAS.

Only writes isolated owner-tagged staging files/containers. Existing Docker
identities are compared before and after. Never prints or exports bearer token.
"""
from __future__ import annotations
import json
import argparse
import secrets
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen

STAGE=Path('/home/andre/projects/openserverdesk/operations/runtime-stage')
BASE='http://127.0.0.1:18690'


def ids():
    return set(subprocess.check_output(
        ['docker','ps','-a','-q','--no-trunc'],text=True,timeout=15).splitlines())


def command(path,content=None,token=None):
    header={'Origin':BASE}
    if token:header['Authorization']='Bearer '+token
    if content is not None:header['Content-Type']='application/json'
    req=Request(BASE+path,headers=header,method='POST' if content is not None else 'GET',
                data=json.dumps(content).encode() if content is not None else None)
    try:
        with urlopen(req,timeout=18) as response:
            return response.status,json.load(response)
    except HTTPError as err:
        return err.code,json.load(err)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--expected-version',required=True)
    expected=parser.parse_args().expected_version
    if expected not in ('0.6.8','0.6.9'):
        raise ValueError('only pinned local staging package versions accepted')
    with urlopen(BASE+'/health',timeout=4) as resp:
        health=json.load(resp)
    assert health['version']==expected,health
    token=(STAGE/'stage-app-manager/token').read_text().strip()
    assert command('/api/v1/stage/apps')[0]==401
    assert command('/api/v1/stage/apps',token=token)[1]['apps']==[]
    assert command('/api/v1/stage/files',token=token)[1]['files']==[]
    assert command('/api/v1/stage/recovery',token=token)[1]['backups']==[]
    original=ids()
    file='installed-release-'+secrets.token_hex(6)+'.txt'
    content='persisted-from-packaged-runtime-'+secrets.token_hex(9)
    app=None
    checkpoint=None
    try:
        code,out=command('/api/v1/stage/files',
                         {'action':'create','name':file,'content':content},token)
        assert code==200,(code,out)
        code,out=command('/api/v1/stage/apps',{'action':'install'},token)
        assert code==200,(code,out)
        app=out['app']['name']
        result=subprocess.check_output(
            ['docker','exec',app,'cat','/stage/files/'+file],
            text=True,timeout=15).strip()
        assert result==content
        code,out=command('/api/v1/stage/recovery',{'action':'checkpoint'},token)
        assert code==200,(code,out)
        checkpoint=out['checkpoint']
        command('/api/v1/stage/files',{'action':'delete','name':file},token)
        code,out=command('/api/v1/stage/files',
                         {'action':'create','name':file,'content':'CORRUPTED'},token)
        assert code==200,(code,out)
        code,out=command('/api/v1/stage/recovery',
                         {'action':'restore','checkpoint':checkpoint},token)
        assert code==200,(code,out)
        code,out=command('/api/v1/stage/files?name='+file,token=token)
        assert code==200 and out['content']==content
        result=subprocess.check_output(
            ['docker','exec',app,'cat','/stage/files/'+file],
            text=True,timeout=15).strip()
        assert result==content
        code,out=command('/api/v1/stage/apps',
                         {'action':'restart','name':app},token)
        assert code==200,(code,out)
        result=subprocess.check_output(
            ['docker','exec',app,'cat','/stage/files/'+file],
            text=True,timeout=15).strip()
        assert result==content
        print('ACTUAL_LIVE_INSTALLED_AUTH_APP_STORAGE_CHECKPOINT_RESTORE_PASS',expected)
        print('APP_STORAGE_PERSISTENCE_AFTER_RESTART_PASS')
    finally:
        if app:
            status,_=command('/api/v1/stage/apps',
                             {'action':'uninstall','name':app},token)
            if status!=200:raise RuntimeError('stage test app cleanup failed')
        code,_=command('/api/v1/stage/files',
                       {'action':'delete','name':file},token)
        if code not in (200,404):
            raise RuntimeError('stage test file cleanup failed')
        if checkpoint:
            code,_=command('/api/v1/stage/recovery',
                           {'action':'delete','checkpoint':checkpoint},token)
            if code!=200:
                raise RuntimeError('stage checkpoint cleanup failed')
        if ids()!=original:
            raise RuntimeError('unexpected existing Docker IDs changed')
        print('ALL_PRODUCTION_DOCKER_IDENTITIES_PRESERVED_PASS',len(original))


if __name__=='__main__':
    main()
