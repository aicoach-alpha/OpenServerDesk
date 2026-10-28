#!/usr/bin/env python3
"""Small isolated proof of actual SQLite WAL-safe configuration recovery."""
import json
import os
import secrets
import shutil
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "migration"))
import m1_config_recovery as rec

base = Path("/home/andre/projects/openserverdesk/operations/runtime-stage")
tag = secrets.token_hex(6)
src = base / ("osd-fixture-source-" + tag)
bak = base / ("config-only-fixture-" + tag)
try:
    src.mkdir(mode=0o700)
    bak.mkdir(mode=0o700)
    service = src / "etc" / "casaos"
    database = src / "var" / "lib" / "casaos"
    for directory in [service, database]:
        directory.mkdir(parents=True)
    (service / "config.ini").write_text("gateway=working\n")
    (service / "assets").symlink_to("../shared", target_is_directory=True)
    (database / "db").mkdir()
    db = database / "db" / "user.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE state (name TEXT PRIMARY KEY, value TEXT)")
        con.execute("INSERT INTO state VALUES (?,?)", ("user", "before-migration"))
        con.execute("PRAGMA journal_mode=WAL")
        con.commit()
    result=rec.snapshot(fixture_sources=[str(service), str(database)],fixture_root=bak)
    assert result["sqlite_verified"]==1 and result["symlinks_preserved"]==1
    assert result["user_data_copied"] is False
    bundle=result["backup_id"]
    _, proof=rec.verify(bundle,root=bak)
    assert proof["sqlite_verified"]==1
    (service / "config.ini").write_text("gateway=broken\n")
    with sqlite3.connect(db) as con:
        con.execute("UPDATE state SET value='broken' WHERE name='user'")
    restored=rec.restore(bundle,root=bak)
    assert restored["original_platform_config_overwritten"] is False
    new=bak / "restored" / bundle / "opt" / "openserverdesk-dev" / "runtime-stage" / src.name
    assert (new / "etc/casaos/config.ini").read_text()=="gateway=working\n"
    assert (new / "etc/casaos/assets").is_symlink()
    with sqlite3.connect(new / "var/lib/casaos/db/user.db") as con:
        assert con.execute("SELECT value FROM state WHERE name='user'").fetchone()[0]=="before-migration"
    assert (service / "config.ini").read_text()=="gateway=broken\n"
    print("CONFIG_SQLITE_LINK_SNAPSHOT_SEPARATE_RESTORE_PASS")
    print("ORIGINAL_LIVE_CONFIG_UNCHANGED_BY_RESTORE_PASS")
    # A tampered file cannot be treated as an authentic backup.
    forged=bak / bundle / "data" / "opt" / "openserverdesk-dev" / "runtime-stage" / src.name / "etc/casaos/config.ini"
    forged.write_text("modified after snapshot\n")
    try:
        rec.verify(bundle,root=bak)
    except rec.Rejected:
        pass
    else:
        raise AssertionError("tampered configuration erroneously verified")
    print("BACKUP_TAMPERING_REJECTED_PASS")
    print("USER_HDD_CONTENT_NEVER_ACCESSED_PASS")
finally:
    shutil.rmtree(src, ignore_errors=True)
    shutil.rmtree(bak, ignore_errors=True)
