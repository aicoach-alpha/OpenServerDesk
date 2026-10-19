#!/usr/bin/env python3
"""Explicit, disposable-only activation and undo of a staged UserService pair.

Never operates on CasaOS production paths, mounted user data, or live services.
"""
import argparse
import json
import tempfile
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
    return resolved

def execute(action, target, bundle=None):
    target = isolated(target)
    if action == "activate":
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
    parser.add_argument("action", choices=("activate", "rollback"))
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    print(json.dumps(execute(args.action, args.target, args.bundle), sort_keys=True))

if __name__ == "__main__":
    main()
