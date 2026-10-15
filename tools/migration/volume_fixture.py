"""Fixture-only application-volume snapshot, refusing symlinks and special files."""
import hashlib
import json
import shutil
import os
import tempfile
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
    if Path(source).is_symlink() or Path(destination).is_symlink():
        raise ValueError("symlink root not allowed")
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
        shutil.copy2(source / rel, target)
    (destination / "manifest.json").write_text(json.dumps(index, sort_keys=True))
    return index


def validate(snapshot_dir):
    snapshot_dir = Path(snapshot_dir)
    if snapshot_dir.is_symlink():
        raise ValueError("symlinked snapshot root")
    snapshot_dir = snapshot_dir.resolve()
    index = json.loads((snapshot_dir / "manifest.json").read_text())
    # Reject symlinks at any depth, including a parent directory of a file.
    list(files(snapshot_dir / "data"))
    for name, expected in index.items():
        name_path = Path(name)
        if name_path.is_absolute() or ".." in name_path.parts:
            raise ValueError("unsafe manifest path")
        value = snapshot_dir / "data" / name
        if not value.is_file() or value.is_symlink() or digest(value) != expected:
            raise ValueError("corrupted snapshot file")
    return len(index)


def restore(snapshot_dir, target, fixture_root):
    """Replace one stopped synthetic fixture tree; never use for running services.

    fixture_root must be an explicitly provisioned scratch directory containing
    both the snapshot and target as direct children.
    """
    for item in (snapshot_dir, target, fixture_root):
        if Path(item).is_symlink():
            raise ValueError("symlinked fixture root")
    snapshot_dir, target, fixture_root = (
        Path(item).resolve() for item in (snapshot_dir, target, fixture_root)
    )
    if snapshot_dir.parent != fixture_root or target.parent != fixture_root:
        raise ValueError("restore must stay within a single scratch fixture")
    if not target.is_dir() or target == snapshot_dir:
        raise ValueError("existing distinct fixture target required")
    validate(snapshot_dir)  # Verify all bytes before any target changes.
    index = json.loads((snapshot_dir / "manifest.json").read_text())
    replacement = Path(tempfile.mkdtemp(prefix=".osd-restore-", dir=fixture_root))
    previous = fixture_root / (".osd-previous-" + replacement.name[13:])
    try:
        for name in index:
            destination = replacement / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(snapshot_dir / "data" / name, destination)
        if {str(p.relative_to(replacement)): digest(p) for p in files(replacement)} != index:
            raise ValueError("restored files did not match manifest")
        os.replace(target, previous)
        try:
            os.replace(replacement, target)
        except Exception:
            os.replace(previous, target)
            raise
        shutil.rmtree(previous)
    finally:
        if replacement.exists():
            shutil.rmtree(replacement)
    return len(index)
