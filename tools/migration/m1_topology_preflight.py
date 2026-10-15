#!/usr/bin/env python3
"""Production-mount migration topology gate (READ ONLY, no data copied).

Reads only the existing private Docker inventory from m1_app_data_inventory.
Uses lstat/statvfs metadata; never opens live content, Docker sockets or
credentials. Identifies nested bind-mounts and shared writable sources that
make a naive per-container copy logically inconsistent.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import stat
import tempfile
from collections import defaultdict
from pathlib import Path

DEFAULT_INPUT=Path('/opt/openserverdesk-dev/runtime-stage/M1_PRIVATE_APP_DATA_INVENTORY.json')
PRIVATE_OUT=Path('/opt/openserverdesk-dev/runtime-stage/M1_PRIVATE_TOPOLOGY_PREFLIGHT.json')
PUBLIC_OUT=Path('/opt/openserverdesk-dev/runtime-stage/M1_PUBLIC_TOPOLOGY_PREFLIGHT.json')


def inside(a,b):
    """Whether path a is strictly nested under path b, without symlink resolution."""
    return a != b and b in a.parents


def analyze(report):
    if report.get('scope')!='READ_ONLY_REAL_DOCKER_APP_DATA_INVENTORY' or report.get('production_modified') is not False:
        raise ValueError('unrecognized source inventory')
    sources=report.get('bind_sources')
    if not isinstance(sources,dict) or not sources:
        raise ValueError('missing real bind sources')
    rows={}
    filesystems=defaultdict(lambda:{'sources':0,'mount_points':set(),'free_bytes':None})
    for name, detail in sources.items():
        if not isinstance(name,str) or not name.startswith('/') or '\\0' in name or not isinstance(detail,dict):
            raise ValueError('unsafe source path')
        path=Path(name)
        if '..' in path.parts or path==Path('/'):
            raise ValueError('ambiguous source path')
        st=path.lstat()
        if stat.S_ISLNK(st.st_mode):
            kind='symlink'
        elif stat.S_ISDIR(st.st_mode):
            kind='directory'
        elif stat.S_ISREG(st.st_mode):
            kind='file'
        else:
            kind='special'
        consumers=detail.get('consumers')
        if not isinstance(consumers,list):
            raise ValueError('invalid consumers')
        writable=sum(bool(c.get('writable')) for c in consumers if isinstance(c,dict))
        fs=os.statvfs(path)
        dev=str(st.st_dev)
        entry=filesystems[dev]
        entry['sources']+=1
        entry['free_bytes']=fs.f_bavail*fs.f_frsize
        entry['mount_points'].add(str(path.anchor))
        rows[name]={'kind':kind,'device':dev,'writable_consumers':writable,
                    'consumer_count':len(consumers),
                    'needs_review':kind not in ('directory','file') or writable>0}
    paths=sorted((Path(k) for k in rows),key=lambda p:(len(p.parts),str(p)))
    nested=[]
    for index,parent in enumerate(paths):
        for child in paths[index+1:]:
            if inside(child,parent):
                nested.append({'parent':str(parent),'child':str(child),
                               'same_device':rows[str(parent)]['device']==rows[str(child)]['device']})
    # Distinct bind paths can reference one filesystem subtree (duplicated
    # snapshots) or a mount nested in another source (must preserve mount
    # boundary and ownership ordering).
    writable=sum(v['writable_consumers'] for v in rows.values())
    shared_writable=sum(v['writable_consumers']>1 for v in rows.values())
    file_count=sum(v['kind']=='file' for v in rows.values())
    special_count=sum(v['kind'] not in ('directory','file') for v in rows.values())
    fs_count=len(filesystems)
    return {
       'schema_version':1,
       'checked_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
       'scope':'real_docker_bind_topology_readonly',
       'source_inventory_checked_at':report.get('checked_at_utc'),
       'production_modified':False,'migration_allowed':False,
       'source_count':len(rows),'directory_sources':len(rows)-file_count-special_count,
       'file_sources':file_count,'special_sources':special_count,
       'writable_bind_consumers':writable,
       'shared_writable_source_count':shared_writable,
       'nested_source_pairs':len(nested),
       'filesystem_count':fs_count,
       'required_gates':[
          'All writable applications quiesced and app-consistent snapshots proven',
          'Deduplicate nested/overlapping sources without crossing volume boundaries',
          'Disk space and external filesystem availability sufficient for snapshot and restoration',
          'Checksum-verified restoration of every real bind and Compose definition',
          'Owner, ACL, UID/GID and filesystem metadata preserved',
          'Application resume and rollback proven using isolated equivalent mounts',
       ],
       'private':{'binds':rows,'nested_sources':nested,
           'filesystems':{k:{'source_count':v['sources'],'free_bytes':v['free_bytes']}
                          for k,v in filesystems.items()}},
    }


def save(path, data, mode):
    if path.is_symlink() or not path.parent.is_dir():
        raise ValueError('unsafe output path')
    fd,temp=tempfile.mkstemp(prefix='.m1-topology-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(data,stream,sort_keys=True,indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp,mode)
        os.replace(temp,path)
    finally:Path(temp).unlink(missing_ok=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--inventory',type=Path,default=DEFAULT_INPUT)
    p.add_argument('--private-report',type=Path,default=PRIVATE_OUT)
    p.add_argument('--public-report',type=Path,default=PUBLIC_OUT)
    args=p.parse_args()
    if args.inventory.is_symlink() or args.inventory.stat().st_size>10_000_000:
        raise ValueError('unsafe input inventory')
    report=analyze(json.loads(args.inventory.read_text()))
    save(args.private_report,report,0o600)
    public={k:v for k,v in report.items() if k!='private'}
    save(args.public_report,public,0o644)
    print(json.dumps(public,sort_keys=True))


if __name__=='__main__':
    main()
