#!/usr/bin/env python3
"""One Docker-backed quiescence -> multi-project snapshot -> restore proof.

Runs only throwaway, labeled, network-disabled containers and disposable
application data under OpenServerDesk staging; production untouched.
"""
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "migration"))
import full_app_recovery as recovery

STAGE = Path("/opt/openserverdesk-dev/runtime-stage")


def docker(*args, check=True):
    p = subprocess.run(["docker", *args], text=True, capture_output=True, timeout=35)
    if check and p.returncode:
        raise RuntimeError("Docker fixture command failed: " + p.stderr[-240:])
    return p.stdout.strip()


def test():
    token = secrets.token_hex(12)
    container = "osd-appbundle-" + token
    root = Path(tempfile.mkdtemp(prefix="app-bundle-", dir=STAGE))
    try:
        (root / "owner.json").write_text(json.dumps({"token": token}))
        a = root / "live" / "project-a"
        b = root / "live" / "project-b"
        for p in (a, b):
            (p / "data").mkdir(parents=True)
        with sqlite3.connect(a / "data" / "app.db") as con:
            con.execute("CREATE TABLE proof (name TEXT PRIMARY KEY, value TEXT)")
            con.execute("INSERT INTO proof VALUES (?,?)", ("persisted", "before_upgrade"))
        (a / "compose.yml").write_text("services:\n  app:\n    image: alpine:3.20\n")
        (b / "data" / "preferences.json").write_text('{"setting":"baseline"}\n')
        (b / "compose.yml").write_text("services:\n  worker:\n    image: alpine:3.20\n")
        # Explicit staged Docker writer proves refusal while active.
        docker("run", "-d", "--name", container,
               "--label", "osd.m1.appbundle-owner=" + token,
               "--network", "none", "--read-only", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--memory", "96m",
               "--pids-limit", "30",
               "--mount", f"type=bind,src={a},dst=/app,readonly",
               "--entrypoint", "/bin/sh", "golang:1.26.8",
               "-c", "sleep 180")
        try:
            recovery.snapshot(root)
        except RuntimeError as error:
            if "stage writer" not in str(error):
                raise
            print("LIVE_STAGE_WRITER_QUIESCENCE_ENFORCED_PASS")
        else:
            raise AssertionError("snapshot allowed while fixture writer active")
        docker("rm", "-f", container)
        report = recovery.snapshot(root)
        assert report["projects"] == 2 and report["files"] == 4
        # Simulate faulty release overwriting local application data.
        with sqlite3.connect(a / "data" / "app.db") as con:
            con.execute("UPDATE proof SET value='corrupted_release'")
        (b / "data" / "preferences.json").unlink()
        restored = recovery.restore(root)
        assert restored["restored_projects"] == 2
        with sqlite3.connect(root / "recovered/project-a/data/app.db") as con:
            assert con.execute("SELECT value FROM proof WHERE name='persisted'").fetchone()[0] == "before_upgrade"
        assert json.loads((root / "recovered/project-b/data/preferences.json").read_text())["setting"] == "baseline"
        assert "services:" in (root / "recovered/project-a/compose.yml").read_text()
        assert "services:" in (root / "recovered/project-b/compose.yml").read_text()
        # A real isolated container mounts data from the recovered tree.
        new_mount = root / "recovered/project-b"
        result = docker("run", "--rm", "--network", "none", "--read-only",
                        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                        "--memory", "64m", "--pids-limit", "20",
                        "--mount", f"type=bind,src={new_mount},dst=/app,readonly",
                        "--entrypoint", "/bin/cat", "golang:1.26.8",
                        "/app/data/preferences.json")
        assert json.loads(result)["setting"] == "baseline"
        print("TWO_REAL_DOCKER_APP_PROJECTS_QUIESCE_BACKUP_RESTORE_AND_BOOT_PASS")
        print("RECOVERED_SQLITE_COMPOSE_AND_EXTERNAL_BIND_DATA_PASS")
        print("PRODUCTION_MODIFIED_FALSE")
    finally:
        docker("rm", "-f", container, check=False)
        shutil.rmtree(root)


if __name__ == "__main__":
    test()
