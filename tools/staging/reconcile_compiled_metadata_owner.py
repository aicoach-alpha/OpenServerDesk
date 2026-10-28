#!/usr/bin/env python3
"""One-time, allowlisted ownership repair for legacy staging metadata only.

Requires root for --apply. NEVER recursively changes ownership and NEVER
touches application volume directories, backups, or credential files.
"""
from __future__ import annotations

import argparse
import json
import os
import pwd
import re
import stat
from pathlib import Path

ROOT = Path("/home/andre/projects/openserverdesk/operations/runtime-stage/stage-app-manager/store-compiled")
PROJECT = re.compile(r"osd-compiled-[a-f0-9]{12}\Z")
REGISTRY = ROOT / "registry.json"
ALLOWED_FILES = ("compose.json", "previous.json", "previous-data.json")
ALLOWED_DIRS = ("data-checkpoints",)


def validate_path(path, kind, uid):
    metadata = path.lstat()
    expected_mode = 0o700 if kind == "dir" else 0o600
    valid_type = stat.S_ISDIR(metadata.st_mode) if kind == "dir" else stat.S_ISREG(metadata.st_mode)
    if (not valid_type or stat.S_IMODE(metadata.st_mode) != expected_mode
            or metadata.st_uid not in (0, uid)
            or metadata.st_gid not in (0, uid)):
        raise RuntimeError("unsafe_compiled_metadata: " + path.name)
    return metadata


def plan():
    if os.geteuid() != 0:
        raise RuntimeError("root_required_to_read_legacy_stage_metadata")
    uid = pwd.getpwnam("andre").pw_uid
    if uid != 1000:
        raise RuntimeError("unexpected_operator_uid")
    validate_path(ROOT, "dir", uid)
    validate_path(REGISTRY, "file", uid)
    data = json.loads(REGISTRY.read_text())
    if not isinstance(data, dict) or len(data) > 2:
        raise RuntimeError("invalid_compiled_stage_registry")
    paths = [REGISTRY]
    for name in sorted(data):
        if not isinstance(name, str) or not PROJECT.fullmatch(name):
            raise RuntimeError("invalid_compiled_stage_project")
        folder = ROOT / name
        validate_path(folder, "dir", uid)
        paths.append(folder)
        for part in ALLOWED_FILES:
            file = folder / part
            if file.exists() or file.is_symlink():
                validate_path(file, "file", uid)
                paths.append(file)
        for part in ALLOWED_DIRS:
            directory = folder / part
            if directory.exists() or directory.is_symlink():
                validate_path(directory, "dir", uid)
                paths.append(directory)
        # Never reconcile ambiguous, interrupted staging operations.
        for part in ("pending.json", "data-restore-pending.json",
                     "online-data-pending.json"):
            file = folder / part
            if file.exists() or file.is_symlink():
                raise RuntimeError("stage_recovery_journal_requires_review")
    return uid, paths, sorted(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    uid, paths, projects = plan()
    changes = [p for p in paths if p.lstat().st_uid != uid or p.lstat().st_gid != uid]
    if args.apply:
        if os.geteuid() != 0:
            raise RuntimeError("root_required_for_metadata_reconciliation")
        for path in changes:
            kind = "dir" if path.is_dir() else "file"
            validate_path(path, kind, uid)
            os.chown(path, uid, uid, follow_symlinks=False)
        for path in paths:
            validate_path(path, "dir" if path.is_dir() else "file", uid)
            if path.lstat().st_uid != uid:
                raise RuntimeError("metadata_reconciliation_incomplete")
    print(json.dumps({"scope": "allowlisted_compiled_stage_metadata_only",
                      "mode": "applied" if args.apply else "dry_run",
                      "registered_projects": projects,
                      "metadata_paths": len(paths),
                      "ownership_changes": len(changes),
                      "application_volumes_touched": False,
                      "snapshots_touched": False,
                      "credentials_touched": False,
                      "production_mutation_allowed": False},sort_keys=True))


if __name__ == "__main__":
    main()
