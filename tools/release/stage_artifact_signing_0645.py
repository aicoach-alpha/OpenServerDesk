#!/usr/bin/env python3
"""Staging artifact provenance: Ed25519 signature over canonical JSON manifest.

Staging-only local operator key; does NOT grant production security acceptance.
Verification is usable without private key or network access.
"""
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

BASE=Path('/home/andre/projects/openserverdesk/operations/build')
VERSION='0.6.45'
PACKAGE=BASE/f'openserverdesk-m1-candidate_{VERSION}_amd64.deb'
DOC=BASE/f'OpenServerDesk-stage-{VERSION}.manifest.json'
SIG=BASE/f'OpenServerDesk-stage-{VERSION}.manifest.sig'
KEY=Path('/home/andre/projects/openserverdesk/operations/signing/staging-ed25519-private.pem')
PUBLIC=Path(__file__).resolve().parents[2]/'security/staging-ed25519-public.pem'
SOURCE_SHA='f665f582ed837d2030d032113e1cf14162e58bd7'


def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for piece in iter(lambda:stream.read(1024*1024),b''):
            h.update(piece)
    return h.hexdigest()


def require(ok,description):
    if not ok:raise RuntimeError(description)


def cmd(*args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=45)
    if result.returncode:raise RuntimeError('cryptographic or metadata validation failed')
    return result.stdout.strip()


def sign():
    require(os.geteuid()==0,'root release operator required')
    require(not DOC.exists() and not SIG.exists(),'stage manifest is immutable once published')
    require(KEY.is_file() and not KEY.is_symlink(),'missing signing key')
    require(PACKAGE.is_file(),'missing package')
    require(cmd('dpkg-deb','--field',str(PACKAGE),'Version')==VERSION,'candidate version changed')
    require(KEY.stat().st_mode & 0o077==0,'unsafe staging private key permissions')
    manifest={
        'schema':1,'artifact':PACKAGE.name,
        'artifact_size_bytes':PACKAGE.stat().st_size,
        'artifact_sha256':sha256(PACKAGE),
        'git_source_sha':SOURCE_SHA,
        'manifest_created_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'signing_algorithm':'Ed25519 over UTF-8 canonical manifest JSON',
        'signing_scope':'local_opensrvdesk_stage_only',
        'production_release_approved':False,
        'independent_security_review_complete':False,
    }
    content=(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n').encode()
    fd=os.open(DOC,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(content)
            stream.flush();os.fsync(stream.fileno())
        cmd('openssl','pkeyutl','-sign','-inkey',str(KEY),'-rawin',
            '-in',str(DOC),'-out',str(SIG))
        SIG.chmod(0o644)
        return verify()
    except Exception:
        SIG.unlink(missing_ok=True)
        DOC.unlink(missing_ok=True)
        raise


def verify():
    require(PACKAGE.is_file() and DOC.is_file() and SIG.is_file(),
            'missing signed release bundle')
    require(not DOC.is_symlink() and not SIG.is_symlink(),'unsafe release metadata')
    manifest=json.loads(DOC.read_text())
    expected={
        'schema','artifact','artifact_size_bytes','artifact_sha256',
        'git_source_sha','manifest_created_at_utc','signing_algorithm',
        'signing_scope','production_release_approved',
        'independent_security_review_complete',
    }
    require(set(manifest)==expected,'unknown stage attestation format')
    require(manifest['schema']==1 and manifest['artifact']==PACKAGE.name,
            'release manifest schema mismatch')
    require(manifest['git_source_sha']==SOURCE_SHA,'unknown source commit')
    require(manifest['artifact_size_bytes']==PACKAGE.stat().st_size,
            'package size changed')
    require(manifest['artifact_sha256']==sha256(PACKAGE),
            'package SHA256 differs from signature manifest')
    require(manifest['production_release_approved'] is False and
            manifest['independent_security_review_complete'] is False and
            manifest['signing_scope']=='local_opensrvdesk_stage_only',
            'staging signature must not claim production acceptance')
    cmd('openssl','pkeyutl','-verify','-pubin','-inkey',str(PUBLIC),
        '-rawin','-in',str(DOC),'-sigfile',str(SIG))
    return {
        'status':'STAGING_ED25519_MANIFEST_SIGNATURE_VERIFIED',
        'package_version':VERSION,
        'source_git_sha':SOURCE_SHA,
        'package_sha256':manifest['artifact_sha256'],
        'production_release_approved':False,
    }


if __name__=='__main__':
    if len(sys.argv)!=2 or sys.argv[1] not in ('sign','verify'):
        raise SystemExit('Usage: stage_artifact_signing.py sign|verify')
    try:
        print(json.dumps(sign() if sys.argv[1]=='sign' else verify(),sort_keys=True))
    except (RuntimeError,OSError,ValueError,subprocess.TimeoutExpired) as exc:
        print('STAGING_SIGNING_FAILED',str(exc),file=sys.stderr)
        raise SystemExit(2)
