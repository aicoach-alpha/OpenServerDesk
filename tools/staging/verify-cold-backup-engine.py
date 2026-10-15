#!/usr/bin/env python3
"""Single end-to-end sealed app-data backup/integrity UAT on isolated real files."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/migration"))
import m1_cold_backup as m

base=Path(tempfile.mkdtemp(prefix="osd-cold-appdata-",dir=m.STAGE))
try:
    stage=base/"stage"
    stage.mkdir()
    backups=stage/"cold-backups"
    backups.mkdir(mode=0o700)
    one=stage/"app-config"
    one.mkdir()
    confile=one/"database.sqlite"
    with sqlite3.connect(confile) as conn:
        conn.execute("CREATE TABLE proof (x TEXT)")
        conn.execute("INSERT INTO proof VALUES ('persisted')")
    (one/"settings.txt").write_text("configuration-v1")
    two=stage/"compose-app.yml"
    two.write_text("services:\n  app:\n    image: busybox:latest\n")
    recovery=stage/"cold-recovery"
    recovery.mkdir(mode=0o700)
    original=m.STAGE,m.BACKUPS,m.RECOVERED,m.collect
    m.STAGE=stage
    m.BACKUPS=backups
    m.RECOVERED=recovery
    data={
        "production_modified":False,
        "container_count":2,
        "running_container_count":0,
        "live_writable_mount_count":0,
        "compose_project_count":1,
        "unique_bind_source_count":1,
        "bind_sources":{str(one):{"file_type":"directory"}},
        "compose_projects":{"fixture":{"file_status":[{"path":str(two),"exists":True,"symlink":False}]}}
    }
    try:
        m.collect=lambda:data
        preflight=m.plan()
        assert preflight["cold_backup_authorized"] is True
        created=m.cold_backup()
        assert created["sources"]==2
        verified=m.verify_bundle(created["id"])
        assert verified["verified_sources"]==2
        backup=backups/created["id"]
        with sqlite3.connect(backup/"data/source-0000/database.sqlite") as conn:
            assert conn.execute("SELECT x FROM proof").fetchone()[0]=="persisted"
        assert (backup/"data/source-0001").read_text().startswith("services:")
        (one/"settings.txt").write_text("bad_release")
        result=m.restore_to_staging(created["id"])
        assert result["restored_sources"]==2
        assert (recovery/created["id"]/"data/source-0000/settings.txt").read_text()=="configuration-v1"
        assert (one/"settings.txt").read_text()=="bad_release"
        (backup/"data/source-0000/settings.txt").write_text("tampered")
        try:
            m.verify_bundle(created["id"])
        except m.BackupRejected:
            pass
        else:
            raise AssertionError("backup tampering incorrectly accepted")
        data["running_container_count"]=2
        data["live_writable_mount_count"]=1
        assert m.plan()["cold_backup_authorized"] is False
        try:
            m.cold_backup()
        except m.BackupRejected as exc:
            assert "COLD_BACKUP_BLOCKED" in str(exc)
        else:raise AssertionError("live container backup incorrectly accepted")
        print("REAL_TWO_SOURCE_SQLITE_AND_COMPOSE_COLD_BACKUP_RESTORE_PASS")
        print("RESTORE_NEW_TREE_WITH_UNTOUCHED_LIVE_ORIGINAL_PASS")
        print("BACKUP_INTEGRITY_TAMPER_REJECTION_PASS")
        print("LIVE_DOCKER_WRITERS_BACKUP_FAIL_CLOSED_PASS")
        print("PRODUCTION_MODIFIED_FALSE")
    finally:
        m.STAGE,m.BACKUPS,m.RECOVERED,m.collect=original
finally:
    shutil.rmtree(base)
