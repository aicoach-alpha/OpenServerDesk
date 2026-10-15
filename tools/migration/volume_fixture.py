"""Fixture-only application-volume snapshot, refusing symlinks and special files."""
import hashlib
import json
import shutil
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(root):
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("unsafe fixture type")
        if path.is_file():
            yield path


def snapshot(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or destination.exists() or not source.is_dir() or source.is_symlink():
        raise ValueError("separate fixture-only directories required")
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("nested fixture destinations forbidden")
    index = {str(p.relative_to(source)): digest(p) for p in files(source)}
    destination.mkdir(mode=0o700)
    for rel in index:
        target = destination / "data" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / rel, target)
    (destination / "manifest.json").write_text(json.dumps(index, sort_keys=True))
    return index


def validate(snapshot_dir):
    snapshot_dir = Path(snapshot_dir).resolve()
    index = json.loads((snapshot_dir / "manifest.json").read_text())
    for name, expected in index.items():
        name_path = Path(name)
        if name_path.is_absolute() or ".." in name_path.parts:
            raise ValueError("unsafe manifest path")
        value = snapshot_dir / "data" / name
        if not value.is_file() or value.is_symlink() or digest(value) != expected:
            raise ValueError("corrupted snapshot file")
    return len(index)
