#!/usr/bin/env python3
"""Explicit, disposable-only activation and undo of a staged UserService pair.

Never operates on CasaOS production paths, mounted user data, or live services.
"""
import argparse
import json
import tempfile
import os
import stat
from pathlib import Path
from journaled_pair import replace_pair, recover

def isolated(path):
    raw = Path(path)
    if raw.is_symlink() or not raw.is_dir():
        raise ValueError("existing non-symlink fixture directory required")
    resolved = raw.resolve(strict=True)
    root = Path(tempfile.gettempdir()).resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError("fixture must be inside temporary directory")
    if any(part.is_symlink() for part in [raw, *raw.parents]):
        raise ValueError("symlinked fixture path forbidden")
    # A path under /tmp is not necessarily disposable: a bind mount or
    # another filesystem can be mounted beneath it. Never cross devices.
    if resolved.stat().st_dev != root.stat().st_dev:
        raise ValueError("fixture must remain on temporary filesystem")
    for part in (resolved, *[p for p in resolved.parents if p == root or root in p.parents]):
        if os.path.ismount(part) and part != root:
            raise ValueError("mounted fixture directory forbidden")
        if part != root and (part.stat().st_mode & stat.S_IWOTH):
            raise ValueError("world-writable fixture ancestry forbidden")
    return resolved

def status(target):
    """Read-only, fail-closed state for interrupted fixture activation."""
    target = isolated(target)
    pending = target / ".osd-undo"
    preparing = target / ".osd-undo-preparing"
    if preparing.exists() or preparing.is_symlink():
        state = "INCOMPLETE_PREPARATION"
    elif pending.is_symlink():
        state = "INVALID_JOURNAL"
    elif pending.is_dir():
        state = "ROLLBACK_AVAILABLE"
    elif pending.exists():
        state = "INVALID_JOURNAL"
    else:
        state = "IDLE"
    return {"scope": "DISPOSABLE_TEMP_FIXTURE_ONLY", "state": state,
            "activation_allowed": state == "IDLE",
            "rollback_required": state == "ROLLBACK_AVAILABLE",
            "migration_allowed": False, "production_modified": False}

def execute(action, target, bundle=None):
    target = isolated(target)
    if action == "status":
        if bundle is not None:
            raise ValueError("status does not accept bundle")
        return status(target)
    current = status(target)
    if action == "activate":
        if not current["activation_allowed"]:
            raise RuntimeError("fixture requires recovery or inspection before activation")
        if bundle is None:
            raise ValueError("bundle required")
        bundle = isolated(bundle)
        if bundle == target or bundle in target.parents or target in bundle.parents:
            raise ValueError("overlapping fixture directories")
        changed = replace_pair(bundle, target)
    elif action == "rollback":
        if bundle is not None:
            raise ValueError("rollback does not accept bundle")
        changed = recover(target)
    else:
        raise ValueError("unknown action")
    return {"scope": "DISPOSABLE_TEMP_FIXTURE_ONLY", "action": action,
            "changed": changed, "production_modified": False,
            "migration_allowed": False}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("activate", "rollback", "status"))
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    print(json.dumps(execute(args.action, args.target, args.bundle), sort_keys=True))

if __name__ == "__main__":
    main()
