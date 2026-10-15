"""Offline SQLite fixture snapshot by SQLite backup API; never target live CasaOS."""
import os
import sqlite3
from pathlib import Path


def snapshot(source, destination):
    source, destination = Path(source), Path(destination)
    if source.is_symlink() or destination.is_symlink():
        raise ValueError("symlinks not permitted")
    source, destination = source.resolve(), destination.resolve()
    if source == destination or not source.is_file() or destination.exists():
        raise ValueError("separate existing source and new destination required")
    # sqlite3.backup provides a consistent snapshot even with WAL enabled.
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=2) as inp:
        with sqlite3.connect(destination) as out:
            inp.backup(out, pages=10, sleep=0.05)
            if out.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("invalid SQLite snapshot")
        with open(destination, "rb") as f:
            os.fsync(f.fileno())
    return destination
