#!/usr/bin/env python3
"""Focused disposable staging lifecycle: real binary, journaled pair rollback, routed health."""
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path("/home/andre/projects/openserverdesk/operations")
sys.path.insert(0, "/home/andre/projects/openserverdesk/main/tools/migration")
from journaled_pair import digest, replace_pair, recover


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    stage = ROOT / "runtime-stage"
    binary = ROOT / "bin/CasaOS-UserService"
    old_binary = ROOT / "bin/CasaOS-UserService-v0430"
    for name in (binary, old_binary):
        if not name.is_file():
            raise RuntimeError("missing real staged binary")
    assert run("docker", "inspect", "osd-m1-gateway", "--format", "{{.HostConfig.NetworkMode}}") == "none"
    with tempfile.TemporaryDirectory(prefix="osd-pair-lifecycle-", dir=stage) as temp:
        t = Path(temp)
        live, bundle = t / "live", t / "bundle"
        live.mkdir()
        bundle.mkdir()
        shutil.copy2(binary, live / "userservice")
        shutil.copy2(old_binary, bundle / "userservice")
        # Real SQLite fixture; intentionally no production or existing staging DB.
        with sqlite3.connect(live / "user.db") as db:
            db.execute("CREATE TABLE fixture (value TEXT)")
            db.execute("INSERT INTO fixture VALUES ('new')")
        with sqlite3.connect(bundle / "user.db") as db:
            db.execute("CREATE TABLE fixture (value TEXT)")
            db.execute("INSERT INTO fixture VALUES ('old')")
        (bundle / "manifest.json").write_text(json.dumps({
            n: digest(bundle / n) for n in ("userservice", "user.db")
        }))
        container = "osd-m1-journal-lifecycle"
        def clean():
            subprocess.run(["docker", "rm", "-f", container], capture_output=True)
        clean()
        try:
            def start():
                run("docker", "run", "-d", "--name", container, "--network", "none",
                    "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                    "--memory", "128m", "--pids-limit", "32",
                    "--mount", f"type=bind,src={live},dst=/fixture,readonly",
                    "--entrypoint", "/bin/sh", "busybox:latest",
                    "-c", "while true; do sleep 2; done")
                assert run("docker", "inspect", container, "--format", "{{.State.Running}}") == "true"
            start()
            clean()  # quiesce fixture consumer before changes
            replace_pair(bundle, live)
            assert digest(live / "userservice") == digest(bundle / "userservice")
            with sqlite3.connect(live / "user.db") as db:
                assert db.execute("SELECT value FROM fixture").fetchone()[0] == "old"
            start()  # restored candidate starts
            clean()  # quiesce before undo recovery
            assert recover(live)
            assert digest(live / "userservice") == digest(binary)
            with sqlite3.connect(live / "user.db") as db:
                assert db.execute("SELECT value FROM fixture").fetchone()[0] == "new"
            start()
            print("FOCUSED_JOURNALED_PAIR_LIFECYCLE_PASS")
        finally:
            clean()


if __name__ == "__main__":
    main()
