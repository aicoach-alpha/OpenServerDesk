"""Durable rollback for *only* owned isolated Compose app data.

A complete stage Compose registry is frozen at checkpoint time. No Docker
volumes, production files, or Nextcloud bind sources are ever inspected.
The data root inode stays intact; Docker mounts remain valid after restore.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import tempfile
from pathlib import Path

from stage_apps import STAGE, guarded, AppError
from stage_compose import _registry, _inspect, _command, _project_dir

BACKUPS = STAGE / "compose-backups"
BACKUP = re.compile(r"compose-backup-[a-f0-9]{12}\Z")
MAX_BACKUPS = 5
FILE = "index.html"
MAX_BYTES = 65536


def _checksum(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def _root():
    if BACKUPS.is_symlink():
        raise AppError("unsafe_stage_compose_backup_root", 503)
    if not BACKUPS.exists():
        BACKUPS.mkdir(mode=0o700)
    if (not BACKUPS.is_dir() or BACKUPS.stat().st_mode & 0o077
            or BACKUPS.stat().st_uid != os.geteuid()):
        raise AppError("unsafe_stage_compose_backup_root", 503)
    return BACKUPS


def _file(name):
    directory = _project_dir(name) / "data"
    if directory.is_symlink() or not directory.is_dir():
        raise AppError("unsafe_stage_compose_data", 503)
    members = list(directory.iterdir())
    if len(members) != 1 or members[0].name != FILE:
        raise AppError("unsupported_stage_compose_data_shape", 409)
    path = members[0]
    metadata = path.lstat()
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
            or metadata.st_size > MAX_BYTES):
        raise AppError("unsafe_stage_compose_data_file", 403)
    return path


def _current():
    registered = _registry()
    if not registered:
        raise AppError("no_stage_compose_projects_to_checkpoint", 409)
    result = {}
    for name, item in sorted(registered.items()):
        status = _inspect(name, item)
        data = _file(name)
        result[name] = {
            "id": item["id"], "owner": item["owner"],
            "template": item["template"], "running": status["running"],
            "sha256": _checksum(data), "bytes": data.stat().st_size,
        }
    return result


def _write_manifest(directory, rows):
    document = directory / "manifest.json"
    with document.open("x") as out:
        json.dump({"version": 1, "projects": rows}, out, sort_keys=True)
        out.flush()
        os.fsync(out.fileno())
    _sync(directory)


def _make_snapshot(destination):
    rows = _current()
    temp = Path(tempfile.mkdtemp(prefix=".compose-checkpoint-", dir=_root()))
    try:
        data = temp / "data"
        data.mkdir(mode=0o700)
        for name, record in rows.items():
            project = data / name
            project.mkdir(mode=0o700)
            source = _file(name)
            if _checksum(source) != record["sha256"]:
                raise AppError("compose_data_changed_during_backup", 409)
            target = project / FILE
            shutil.copyfile(source, target)
            os.chmod(target, 0o600)
            if _checksum(source) != record["sha256"] or _checksum(target) != record["sha256"]:
                raise AppError("compose_data_snapshot_integrity_failure", 409)
        _write_manifest(temp, rows)
        os.replace(temp, destination)
        _sync(BACKUPS)
        return rows
    finally:
        if temp.exists(): shutil.rmtree(temp)


def _validated(folder, *, check_current=True):
    if folder.is_symlink() or not folder.is_dir():
        raise AppError("stage_compose_checkpoint_not_found", 404)
    doc = folder / "manifest.json"
    if doc.is_symlink() or not doc.is_file() or doc.stat().st_size > 120000:
        raise AppError("stage_compose_manifest_invalid", 403)
    try:
        raw = json.loads(doc.read_text())
    except (OSError, ValueError):
        raise AppError("stage_compose_manifest_invalid", 403)
    if not isinstance(raw, dict) or set(raw) != {"version", "projects"} or raw["version"] != 1:
        raise AppError("stage_compose_manifest_invalid", 403)
    entries = raw["projects"]
    now = _registry()
    if not isinstance(entries, dict) or not entries or set(entries) != set(now):
        raise AppError("stage_compose_project_set_changed", 409)
    data_root = folder / "data"
    if data_root.is_symlink() or not data_root.is_dir():
        raise AppError("stage_compose_snapshot_missing_data", 409)
    if {p.name for p in data_root.iterdir()} != set(entries):
        raise AppError("stage_compose_snapshot_contains_unknown_data", 409)
    for name, e in entries.items():
        item = now[name]
        if (not isinstance(e, dict)
                or set(e) != {"id","owner","template","running","sha256","bytes"}
                or e["id"] != item["id"] or e["owner"] != item["owner"]
                or e["template"] != item["template"]
                or type(e["running"]) is not bool
                or type(e["bytes"]) is not int
                or not 0 <= e["bytes"] <= MAX_BYTES
                or not isinstance(e["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", e["sha256"])):
            raise AppError("stage_compose_checkpoint_identity_changed", 403)
        original = _inspect(name, item)
        if not original["isolated"]:
            raise AppError("stage_compose_owner_invalid", 403)
        candidate_dir = data_root / name
        if candidate_dir.is_symlink() or not candidate_dir.is_dir():
            raise AppError("unsafe_compose_backup_directory", 403)
        members=list(candidate_dir.iterdir())
        if len(members)!=1 or members[0].name!=FILE:
            raise AppError("unmanifested_stage_compose_backup_data", 409)
        source = candidate_dir / FILE
        if source.is_symlink() or source.stat().st_nlink != 1 or source.stat().st_size != e["bytes"]:
            raise AppError("unsafe_compose_backup_file", 403)
        if _checksum(source) != e["sha256"]:
            raise AppError("stage_compose_snapshot_corrupt", 409)
    return entries


def list_backups():
    with guarded():
        folder = _root()
        names = sorted(p for p in folder.iterdir() if BACKUP.fullmatch(p.name))
        return {
            "backups": [
                {"id": p.name, "projects": len(_validated(p))}
                for p in names
            ],
            "pending_recovery": (folder / "pending").exists(),
            "production_mutation_allowed": False,
        }


def checkpoint():
    with guarded():
        root = _root()
        if (root / "pending").exists() or (root / "pending").is_symlink():
            raise AppError("stage_compose_recovery_pending", 409)
        if sum(bool(BACKUP.fullmatch(p.name)) for p in root.iterdir()) >= MAX_BACKUPS:
            raise AppError("stage_compose_backup_limit", 409)
        identifier = "compose-backup-" + secrets.token_hex(6)
        rows = _make_snapshot(root / identifier)
        return {"checkpoint": identifier, "projects": len(rows),
                "production_mutation_allowed": False}


def _apply(entries, folder):
    registered = _registry()
    for name, entry in entries.items():
        if _inspect(name, registered[name])["running"]:
            _command("docker", "stop", "--time", "2", entry["id"])
    for name, entry in entries.items():
        dst = _file(name)
        source = folder / "data" / name / FILE
        if _checksum(source) != entry["sha256"]:
            raise AppError("compose_snapshot_changed_during_restore", 409)
        temp = dst.parent / (".compose-restore-" + secrets.token_hex(6))
        try:
            with temp.open("xb") as output, source.open("rb") as stream:
                shutil.copyfileobj(stream, output)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temp, 0o600)
            os.replace(temp, dst)
        finally: temp.unlink(missing_ok=True)
        if _checksum(dst) != entry["sha256"]:
            raise AppError("compose_restore_failed_integrity", 409)
    for name, entry in entries.items():
        if entry["running"]:
            _command("docker", "start", entry["id"])


def restore(name):
    if not isinstance(name, str) or not BACKUP.fullmatch(name):
        raise AppError("bad_stage_compose_backup_id", 400)
    with guarded(allow_pending=True):
        root = _root()
        pending = root / "pending"
        if pending.exists() or pending.is_symlink():
            raise AppError("pending_compose_undo_must_be_recovered_first", 409)
        source = root / name
        desired = _validated(source)
        _make_snapshot(pending)
        try:
            _apply(desired, source)
            shutil.rmtree(pending)
            _sync(root)
            return {"restored": name, "projects": len(desired),
                    "original_user_data_modified": False,
                    "production_mutation_allowed": False}
        except Exception:
            try:
                undo = _validated(pending)
                _apply(undo, pending)
                shutil.rmtree(pending)
                _sync(root)
            except Exception as failure:
                raise AppError("compose_rollback_failed_undo_pending", 503) from failure
            raise AppError("compose_rollback_failed_undo_applied", 503)


def recover():
    with guarded(allow_pending=True):
        root = _root()
        pending = root / "pending"
        if pending.is_symlink() or not pending.is_dir():
            raise AppError("no_pending_compose_undo", 404)
        entries = _validated(pending)
        _apply(entries, pending)
        shutil.rmtree(pending)
        _sync(root)
        return {"recovered": "pre_restore_stage_compose_state",
                "production_mutation_allowed": False}


def delete(name):
    if not isinstance(name, str) or not BACKUP.fullmatch(name):
        raise AppError("bad_stage_compose_backup_id", 400)
    with guarded():
        root = _root()
        source = root / name
        _validated(source)
        shutil.rmtree(source)
        _sync(root)
        return {"deleted": name, "production_mutation_allowed": False}
