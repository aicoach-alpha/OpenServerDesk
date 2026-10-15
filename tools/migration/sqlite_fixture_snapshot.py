"""Fixture-only SQLite backup API snapshot with verified staged publication."""
import os
import sqlite3
import tempfile
from pathlib import Path


def snapshot(source, destination):
    source, destination = Path(source), Path(destination)
    if source.is_symlink() or destination.is_symlink():
        raise ValueError("symlinks not permitted")
    source, destination = source.resolve(), destination.resolve()
    if source == destination or not source.is_file() or destination.exists():
        raise ValueError("separate existing source and new destination required")
    # Stage in the destination directory. Failure never publishes a partial backup.
    fd, staged = tempfile.mkstemp(prefix=".osd-sqlite-", suffix=".db", dir=destination.parent)
    os.close(fd)
    staged = Path(staged)
    try:
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=2) as inp:
            with sqlite3.connect(staged) as out:
                inp.backup(out, pages=10, sleep=0.05)
                if out.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("invalid SQLite snapshot")
        with staged.open("rb") as f:
            os.fsync(f.fileno())
        # Refuse pre-existing destination, including concurrent publication.
        os.link(staged, destination)
        dirfd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
        return destination
    finally:
        staged.unlink(missing_ok=True)
