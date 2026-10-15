#!/usr/bin/env python3
"""Fail-closed, offline binary + SQLite pair restore for disposable staging fixtures.

This is a staging rehearsal primitive, NOT a live CasaOS migration tool.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rollback(bundle, target, fail_after_first=False):
    bundle, target = Path(bundle).resolve(), Path(target).resolve()
    manifest = json.loads((bundle / "manifest.json").read_text())
    names = ("userservice", "user.db")
    if set(manifest) != set(names):
        raise ValueError("exact binary/database pair required")
    for name in names:
        source = bundle / name
        if not source.is_file() or source.is_symlink() or sha(source) != manifest[name]:
            raise ValueError("invalid snapshot: " + name)
    with sqlite3.connect(f"file:{bundle / 'user.db'}?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("invalid SQLite snapshot")
    if not target.is_dir() or target.is_symlink():
        raise ValueError("isolated target directory required")
    for name in names:
        if not (target / name).is_file() or (target / name).is_symlink():
            raise ValueError("target incomplete")
    old = {name: (target / name).read_bytes() for name in names}
    try:
        for i, name in enumerate(names):
            replacement = target / (name + ".incoming")
            replacement.write_bytes((bundle / name).read_bytes())
            os.replace(replacement, target / name)
            if i == 0 and fail_after_first:
                raise RuntimeError("injected crash between pair replacements")
    except Exception:
        for name in names:
            recovery = target / (name + ".recover")
            recovery.write_bytes(old[name])
            os.replace(recovery, target / name)
        raise
    return {name: sha(target / name) == manifest[name] for name in names}


if __name__ == "__main__":
    print("Fixture-only library; use test_atomic_pair_rollback.py")
