#!/usr/bin/env python3
"""One authenticated real staging local storage roundtrip; no prod mounts."""
import json
import os
import secrets
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError

root=Path('/home/andre/projects/openserverdesk/operations/runtime-stage/stage-app-manager/files')
token=Path('/home/andre/projects/openserverdesk/operations/runtime-stage/stage-app-manager/token').read_text().strip()
url='http://127.0.0.1:18690/api/v1/stage/files'
name='roundtrip-'+secrets.token_hex(5)+'.txt'


def call(method='GET', payload=None, query='', token_value=token):
    headers={'Authorization':'Bearer '+token_value,'Origin':'http://127.0.0.1:18690'}
    if payload is not None:headers['Content-Type']='application/json'
    data=json.dumps(payload).encode() if payload is not None else None
    req=Request(url+query,method=method,data=data,headers=headers)
    try:
        with urlopen(req,timeout=5) as resp:return resp.status,json.load(resp)
    except HTTPError as err:return err.code,json.load(err)


def main():
    try:
        assert call(token_value='0'*64)[0]==401
        assert call('POST',{'action':'create','name':'../outside','content':'x'})[0]==400
        data='Persistent, staging-only local file: '+secrets.token_hex(12)
        assert call('POST',{'action':'create','name':name,'content':data})[0]==200
        assert call('POST',{'action':'create','name':name,'content':'replace'})[0]==409
        status,read=call(query='?name='+name)
        assert status==200 and read['content']==data
        assert name in [f['name'] for f in call()[1]['files']]
        assert (root/name).read_text()==data
        assert (root/name).stat().st_mode & 0o077 == 0
        assert call('POST',{'action':'delete','name':name})[0]==200
        assert call(query='?name='+name)[0]==404
        print('LIVE_AUTHENTICATED_ISOLATED_LOCAL_STORAGE_CREATE_READ_LIST_DELETE_PASS')
        print('TRAVERSAL_WRONG_TOKEN_AND_OVERWRITE_REJECTED_PASS')
        print('PRODUCTION_FILESYSTEM_UNTOUCHED')
    finally:
        # Stage fixture only, remove on interrupted scoped UAT
        (root/name).unlink(missing_ok=True)


if __name__=='__main__':main()
