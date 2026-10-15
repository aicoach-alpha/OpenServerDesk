#!/usr/bin/env python3
"""Multi-project application data snapshot/restore for isolated M1 fixtures only.

A stage-owner Docker label must have NO running containers before copying.
A backup is atomically published, verified before any recovery, and restored
into a NEW path. Never writes to the source or to production data.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from volume_fixture import files, digest

STAGING = Path("/opt/openserverdesk-dev/runtime-stage")
PROJECT = re.compile(r"[a-z][a-z0-9-]{0,49}\Z")
TOKEN = re.compile(r"[0-9a-f]{24}\Z")


def root_fixture(path):
    path = Path(path)
    if path.is_symlink() or not path.name.startswith("app-bundle-"):
        raise ValueError("only an isolated staging fixture is allowed")
    root = path.resolve(strict=True)
    if root.parent != STAGING.resolve(strict=True) or not root.is_dir():
        raise ValueError("fixture outside staging is forbidden")
    return root


def owner(root):
    path = root / "owner.json"
    if path.is_symlink():
        raise ValueError("symlinked owner marker")
    raw = json.loads(path.read_text())
    token = raw.get("token") if isinstance(raw, dict) else None
    if not isinstance(token, str) or not TOKEN.fullmatch(token) or set(raw) != {"token"}:
        raise ValueError("invalid stage owner")
    return token


def quiesced(root):
    token = owner(root)
    p = subprocess.run(
        ["docker", "ps", "--quiet", "--no-trunc",
         "--filter", "label=osd.m1.appbundle-owner=" + token],
        capture_output=True, text=True, timeout=20)
    if p.returncode:
        raise RuntimeError("cannot prove Docker stage writer quiescence")
    if p.stdout.strip():
        raise RuntimeError("active stage writer: backup/restore denied")
    return token


def scan(tree):
    if tree.is_symlink() or not tree.is_dir():
        raise ValueError("unsafe project data tree")
    result = {}
    for i, path in enumerate(files(tree)):
        if i >= 50000:
            raise ValueError("fixture too large")
        name = str(path.relative_to(tree))
        result[name] = {"sha256": digest(path),
                        "bytes": path.stat().st_size,
                        "mode": path.stat().st_mode & 0o777}
    return result


def projects(source):
    if source.is_symlink() or not source.is_dir():
        raise ValueError("missing project tree")
    selected = sorted(source.iterdir())
    if not selected or len(selected) > 100:
        raise ValueError("invalid project count")
    if any(not PROJECT.fullmatch(p.name) or p.is_symlink() or not p.is_dir()
           for p in selected):
        raise ValueError("unsafe project name/type")
    return selected


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def snapshot(path):
    root = root_fixture(path)
    token = quiesced(root)
    live = root / "live"
    bundle = root / "bundle"
    if bundle.exists() or bundle.is_symlink():
        raise ValueError("backup already exists")
    before = {p.name: scan(p) for p in projects(live)}
    preparing = Path(tempfile.mkdtemp(prefix=".app-bundle-build-", dir=root))
    try:
        for project in before:
            shutil.copytree(live / project, preparing / "data" / project,
                            symlinks=True, copy_function=shutil.copy2)
        after = {p.name: scan(p) for p in projects(preparing / "data")}
        if before != after:
            raise RuntimeError("staging data changed during snapshot")
        manifest = {"format": 1, "owner": token, "projects": before}
        doc = preparing / "manifest.json"
        with doc.open("x") as stream:
            json.dump(manifest, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        sync_dir(preparing)
        os.replace(preparing, bundle)
        sync_dir(root)
        return {"projects": len(before), "files": sum(map(len, before.values())),
                "manifest_sha256": digest(bundle / "manifest.json"),
                "production_modified": False}
    finally:
        if preparing.exists(): shutil.rmtree(preparing)


def restore(path):
    root = root_fixture(path)
    token = quiesced(root)
    bundle = root / "bundle"
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("missing bundle")
    manifest_path = bundle / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("unsafe bundle manifest")
    doc = json.loads(manifest_path.read_text())
    if set(doc) != {"format", "owner", "projects"} or doc["format"] != 1 or doc["owner"] != token:
        raise ValueError("unknown or foreign backup")
    if not isinstance(doc["projects"], dict) or not doc["projects"]:
        raise ValueError("empty manifest")
    entries = projects(bundle / "data")
    expected = doc["projects"]
    if set(expected) != {p.name for p in entries}:
        raise ValueError("project set changed")
    if {p.name: scan(p) for p in entries} != expected:
        raise ValueError("backup data integrity failure")
    dest = root / "recovered"
    if dest.exists() or dest.is_symlink():
        raise ValueError("never overwrite recovered data")
    preparing = Path(tempfile.mkdtemp(prefix=".app-bundle-restore-", dir=root))
    try:
        for p in entries:
            shutil.copytree(p, preparing / p.name, symlinks=True,
                            copy_function=shutil.copy2)
        if {p.name: scan(p) for p in projects(preparing)} != expected:
            raise RuntimeError("restored data hash mismatch")
        os.replace(preparing, dest)
        sync_dir(root)
        return {"restored_projects": len(entries),
                "restored_files": sum(map(len, expected.values())),
                "original_live_data_modified": False}
    finally:
        if preparing.exists(): shutil.rmtree(preparing)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("snapshot", "restore"))
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    result = snapshot(args.fixture) if args.action == "snapshot" else restore(args.fixture)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
