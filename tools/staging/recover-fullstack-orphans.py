#!/usr/bin/env python3
"""Recover only cryptographically named, label-owned M1 disposable stack resources.

Does not inspect or alter non-fixture Docker assets. A separate process can
recover after the orchestration process is killed without executing finally.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

STAGE = Path("/opt/openserverdesk-dev/runtime-stage")
SUFFIXES = ("gw", "bus", "user")
VOLUMES = ("us", "bs", "ub", "bb", "ur", "br")


def docker(*args):
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError(result.stderr[-250:])
    return result.stdout.strip()


def inspect(kind, name):
    result = subprocess.run(["docker", kind, "inspect", name],
                            capture_output=True, text=True, timeout=15)
    if result.returncode:
        if "No such" in result.stderr:
            return None
        raise RuntimeError(result.stderr[-250:])
    return json.loads(result.stdout)[0]


def recover(token):
    if not re.fullmatch(r"[a-f0-9]{14}", token):
        raise ValueError("invalid staging recovery token")
    path = STAGE / ("osd-m1-crash-" + token + ".json")
    if path.is_symlink() or not path.is_file():
        raise ValueError("staging recovery journal missing")
    record = json.loads(path.read_text())
    prefix = "osd-m1-fixture-" + token
    containers = [prefix + "-" + suffix for suffix in SUFFIXES]
    volumes = [prefix + "-" + suffix for suffix in VOLUMES]
    if record.get("token") != token or record.get("containers") != containers or record.get("volumes") != volumes:
        raise ValueError("recovery journal names mismatch")
    scratch = Path(record.get("scratch", ""))
    if scratch.is_symlink() or scratch.parent != STAGE or not scratch.name.startswith("m1-fullstack-"):
        raise ValueError("unsafe scratch path")
    # Verify all existing resource labels before deleting even one resource.
    for name in containers:
        item = inspect("container", name)
        if item and (item["Config"]["Labels"].get("osd.m1.owner") != token or
                     item["Config"]["Labels"].get("osd.m1.fixture") != "true"):
            raise RuntimeError("refusing non-owned container")
    for name in volumes:
        item = inspect("volume", name)
        if item and (item["Labels"].get("osd.m1.owner") != token or
                     item["Labels"].get("osd.m1.fixture") != "true"):
            raise RuntimeError("refusing non-owned volume")
    for name in reversed(containers):
        if inspect("container", name):
            docker("rm", "-f", name)
    for name in reversed(volumes):
        if inspect("volume", name):
            docker("volume", "rm", name)
    if scratch.exists():
        shutil.rmtree(scratch)
    path.unlink()
    print("CRASHED_STAGING_STACK_RECOVERED_PASS")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: recover-fullstack-orphans.py <fixture-token>")
    recover(sys.argv[1])
