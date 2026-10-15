"""Offline fixture-only, recoverable pair replacement with persistent undo journal.

Single writer and stopped consumers required; not a production migration tool.
"""
import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def syncdir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save(src, dest):
    with open(src, "rb") as inp, open(dest, "xb") as out:
        shutil.copyfileobj(inp, out)
        out.flush()
        os.fsync(out.fileno())


def recover(target):
    target = Path(target).resolve()
    journal = target / ".osd-undo"
    if not journal.exists():
        return False
    manifest = json.loads((journal / "manifest.json").read_text())
    if set(manifest) != {"userservice", "user.db"}:
        raise RuntimeError("unexpected recovery journal")
    for name, expected in manifest.items():
        if digest(journal / name) != expected:
            raise RuntimeError("corrupted undo journal")
    for name in ("userservice", "user.db"):
        tmp = target / (name + ".recover")
        tmp.unlink(missing_ok=True)
        save(journal / name, tmp)
        os.replace(tmp, target / name)
    syncdir(target)
    shutil.rmtree(journal)
    syncdir(target)
    return True


def replace_pair(bundle, target):
    bundle = Path(bundle).resolve()
    target = Path(target).resolve()
    if not target.is_dir() or target.is_symlink() or bundle == target:
        raise ValueError("isolated directories required")
    if (target / ".osd-undo").exists():
        raise RuntimeError("pending undo; recover first")
    manifest = json.loads((bundle / "manifest.json").read_text())
    if set(manifest) != {"userservice", "user.db"}:
        raise ValueError("paired snapshot required")
    for name, expected in manifest.items():
        if (bundle / name).is_symlink() or digest(bundle / name) != expected:
            raise ValueError("snapshot checksum mismatch")
        if not (target / name).is_file() or (target / name).is_symlink():
            raise ValueError("incomplete target")
    with sqlite3.connect(f"file:{bundle / 'user.db'}?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("invalid SQLite")
    journal = target / ".osd-undo"
    journal.mkdir(mode=0o700)
    for name in ("userservice", "user.db"):
        save(target / name, journal / name)
    undo = {name: digest(journal / name) for name in ("userservice", "user.db")}
    (journal / "manifest.json").write_text(json.dumps(undo))
    with (journal / "manifest.json").open("rb") as f:
        os.fsync(f.fileno())
    syncdir(journal)
    syncdir(target)
    for name in ("userservice", "user.db"):
        tmp = target / (name + ".next")
        tmp.unlink(missing_ok=True)
        save(bundle / name, tmp)
        os.replace(tmp, target / name)
        syncdir(target)
    return True
