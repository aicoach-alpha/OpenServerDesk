#!/usr/bin/env python3
"""M1.4 in-place migration installer pre-activation gate. No production mutations."""
import argparse, hashlib, json, os, subprocess
from pathlib import Path
import migration_preflight as preflight
import backup_restore as backup

def sha256(p):
    return backup.digest(p)

def gate(archive, candidate=None):
    state=preflight.inspect()
    failures=[k for k,v in state["checks"].items() if not v]
    if not archive.is_file():
        failures.append("backup_missing")
    else:
        try:
            proof=backup.rehearse(archive)
            if proof["sqlite_verified"]<3:failures.append("incomplete_casaos_db_backup")
        except Exception as e:
            failures.append("backup_invalid:"+type(e).__name__)
            proof=None
    package=None
    if candidate:
        if not candidate.is_file() or candidate.suffix!=".deb":
            failures.append("candidate_missing_or_not_deb")
        else:
            info=subprocess.run(["dpkg-deb","--field",str(candidate),"Package","Version","Architecture"],
                                capture_output=True,text=True,timeout=10)
            if info.returncode:failures.append("invalid_deb")
            else:package={"metadata":info.stdout.strip(),"sha256":sha256(candidate)}
    else:
        failures.append("signed_candidate_not_provided")
    return {"step":"M1.4","mode":"non_mutating_staging_gate",
            "casaos_version":state["casaos_version"],
            "backup":str(archive),"backup_sha256":sha256(archive) if archive.is_file() else None,
            "restore_rehearsal":proof if archive.is_file() else None,
            "candidate":package,"checks":state["checks"],
            "failures":failures,"safe_to_activate":False,
            "activation_implemented":False,
            "rollback_implemented":False,
            "note":"Fails closed: requires signed candidate, isolated install rehearsal, and tested rollback before activation"}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--backup",required=True,type=Path)
    p.add_argument("--candidate",type=Path)
    p.add_argument("--report",type=Path)
    args=p.parse_args()
    result=gate(args.backup,args.candidate)
    text=json.dumps(result,indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(text+"\n")
    print(text)
if __name__=="__main__":main()
