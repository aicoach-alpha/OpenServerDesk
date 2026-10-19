#!/usr/bin/env python3
"""M1.4 in-place migration installer pre-activation gate. No production mutations."""
import argparse, hashlib, json, os, subprocess
from pathlib import Path
import migration_preflight as preflight
import backup_restore as backup
from m1_fixture_activation import execute as fixture_execute
from full_app_recovery import snapshot as app_snapshot, restore as app_restore

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
    p.add_argument("--fixture-action", choices=("status", "activate", "rollback"),
                   help="disposable temporary fixture only; never performs production cutover")
    p.add_argument("--fixture-target", type=Path)
    p.add_argument("--fixture-bundle", type=Path)
    p.add_argument("--app-fixture-action", choices=("snapshot", "restore"),
                   help="multi-project isolated staging snapshot/restore only")
    p.add_argument("--app-fixture", type=Path)
    p.add_argument("--backup",type=Path)
    p.add_argument("--candidate",type=Path)
    p.add_argument("--report",type=Path)
    args=p.parse_args()
    if args.app_fixture_action:
        if (not args.app_fixture or args.fixture_action or args.fixture_target
                or args.fixture_bundle or args.backup or args.candidate):
            p.error("app fixture mode requires --app-fixture only")
        result = (app_snapshot(args.app_fixture) if args.app_fixture_action == "snapshot"
                  else app_restore(args.app_fixture))
    elif args.fixture_action:
        if args.backup or args.candidate or not args.fixture_target:
            p.error("fixture mode requires --fixture-target and forbids --backup/--candidate")
        result = fixture_execute(args.fixture_action, args.fixture_target, args.fixture_bundle)
    else:
        if args.fixture_target or args.fixture_bundle or args.app_fixture:
            p.error("fixture arguments require --fixture-action")
        if not args.backup:
            p.error("--backup required for production read-only preflight")
        result=gate(args.backup,args.candidate)
    text=json.dumps(result,indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(text+"\n")
    print(text)
if __name__=="__main__":main()
