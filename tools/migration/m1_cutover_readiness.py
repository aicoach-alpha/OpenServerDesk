#!/usr/bin/env python3
"""Production-boundary-preserving LIVE dry-run: NEVER executes a cutover.

Only Docker *metadata* and approved CasaOS platform configuration snapshots
are verified. Never reads/writes Nextcloud uploads, user bind contents,
Docker app volumes or any production service data outside selected platform
configuration. Never changes an existing production process or mount.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from m1_config_recovery import BACKUP_ROOT, sha, verify, verify_tree
from m1_platform_scope import protected, select
from m1_service_unit_backup import NAMES, inventory as service_inventory

STAGE = Path("/home/andre/projects/openserverdesk/operations/runtime-stage")
LIVE_BACKUP_RECORD = STAGE / "M1_CONFIG_ONLY_SSD_BACKUP_LIVE_20261016.json"
PRIVATE = STAGE / "M1_CUTOVER_PLAN_PRIVATE.json"
PUBLIC = STAGE / "M1_CUTOVER_PLAN_PUBLIC.json"
VERSION = 1
CRITERIA = (
    "platform_scope_not_user_data",
    "backup_on_independent_ssd",
    "backed_up_platform_source_set_matches_current",
    "verified_ssd_snapshot_and_independent_restore",
    "six_casaos_units_healthy",
    "cross_service_consistent_snapshot",
    "production_switch_and_undo_rehearsed",
    "independent_security_and_signed_release",
    "explicit_maintenance_authorization",
)
assert len(CRITERIA) == 9


class NotReady(RuntimeError):
    pass


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def existing(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 40000:
        raise NotReady("invalid private acceptance record")
    return json.loads(path.read_text())


def normalized_selected(paths):
    # Config scope may have selected overlapping roots; snapshot builder
    # deduplicates descendants without accessing user data.
    paths = sorted({Path(x) for x in paths}, key=lambda p: (len(p.parts), str(p)))
    selected = []
    for p in paths:
        if protected(p) or ".." in p.parts:
            raise NotReady("protected/user path attempted in cutover plan")
        if not any(parent == p or parent in p.parents for parent in selected):
            selected.append(p)
    return selected


def check_backup(sources):
    record = existing(LIVE_BACKUP_RECORD)
    backup_id = record.get("backup_id")
    if not isinstance(backup_id, str):
        raise NotReady("no verified platform snapshot")
    manifest, backup_count = verify(backup_id)
    recovery_path = BACKUP_ROOT / "restored" / backup_id
    restored = verify_tree(recovery_path, manifest)
    assert manifest["scope"] == "CASAOS_PLATFORM_CONFIG_ONLY"
    assert manifest["user_data_copied"] is False
    if not all([
        record.get("production_modified") is False,
        record.get("user_data_copied") is False,
        record.get("backup_device_is_ssd") is True,
        record.get("manifest_sha256") == sha(BACKUP_ROOT / backup_id / "manifest.json"),
        record.get("application_consistent_cluster_snapshot") is False,
        record.get("files_verified") == backup_count["files_verified"],
        backup_count == restored,
        backup_count["sqlite_verified"] >= 3,
    ]):
        raise NotReady("platform configuration backup/restore failed verification")
    if not BACKUP_ROOT.is_dir() or BACKUP_ROOT.is_symlink() or not BACKUP_ROOT.is_relative_to(
        Path("/mnt/ssd-turbo")
    ):
        raise NotReady("unexpected platform backup target")
    if BACKUP_ROOT.stat().st_mode & 0o077:
        raise NotReady("backup not root-private")
    if not Path("/mnt/ssd-turbo").is_mount():
        raise NotReady("dedicated backup SSD offline")
    source_devices = {p.lstat().st_dev for p in sources}
    if BACKUP_ROOT.stat().st_dev in source_devices:
        raise NotReady("backup shares filesystem with platform configuration")
    # Snapshot's original absolute selected platform root entries must agree
    # with all current selected platform roots; this can be checked purely
    # from the restore manifest's path names (no user files accessed).
    backed = {p for p in (str(Path("/") / k) for k in manifest["entries"])
              if p in {str(s) for s in sources}}
    if len(backed) != len(sources):
        raise NotReady("platform source set changed since snapshot")
    return {
        "backup_id": backup_id,
        "sources": len(sources),
        "files": backup_count["files_verified"],
        "sqlite_databases": backup_count["sqlite_verified"],
        "backup_manifest_hash": record["manifest_sha256"],
        "ssd_distinct_fs": True,
    }


def assess():
    current, candidate_paths = select()
    selected = normalized_selected(candidate_paths)
    if not selected or not all(not protected(p) for p in selected):
        raise NotReady("safe platform configuration selection unavailable")
    gates = {key: False for key in CRITERIA}
    gates["platform_scope_not_user_data"] = (
        current["external_user_data_copied"] is False
        and current["external_user_data_inspected"] is False)
    metadata = {}
    try:
        backup = check_backup(selected)
    except (OSError, ValueError, TypeError, KeyError, AssertionError, NotReady) as err:
        backup = None
        metadata["backup_issue"] = type(err).__name__
    if backup:
        gates["backup_on_independent_ssd"] = True
        gates["backed_up_platform_source_set_matches_current"] = True
        gates["verified_ssd_snapshot_and_independent_restore"] = True
        metadata.update({
            "verified_config_files": backup["files"],
            "verified_sqlite_databases": backup["sqlite_databases"],
        })
    try:
        units = service_inventory()
    except (OSError, ValueError, RuntimeError) as err:
        units = None
        metadata["service_issue"] = type(err).__name__
    gates["six_casaos_units_healthy"] = (
        isinstance(units, dict)
        and set(units) == set(NAMES)
        and all(v["state"] == "active" for v in units.values())
    )
    # These four high-stakes release gates require independent evidence
    # AND a separate, explicit user maintenance authorization. Never infer
    # them from staging boot, SQLite integrity, or HTTP200.
    for key in ("cross_service_consistent_snapshot",
                "production_switch_and_undo_rehearsed",
                "independent_security_and_signed_release",
                "explicit_maintenance_authorization"):
        gates[key] = False
    report = {
        "schema_version": VERSION,
        "checked_at_utc": stamp(),
        "scope": "CASAOS_PLATFORM_CONFIG_ONLY_NO_USER_DATA_MIGRATION",
        "production_modified": False,
        "migration_allowed": False,
        "user_data_content_accessed": False,
        "external_hdd_backup_required": False,
        "running_containers": current["running_container_count"],
        "compose_projects": current["compose_project_count"],
        "protected_bind_references_preserved": current["protected_bind_references_skipped"],
        "selected_platform_config_sources": len(selected),
        "verified_config_files": metadata.get("verified_config_files", 0),
        "verified_sqlite_databases": metadata.get("verified_sqlite_databases", 0),
        "gates": gates,
        "pending_gates": [k for k in CRITERIA if not gates[k]],
        "next_priority": "Implement cross-service consistency and stage an independently verified full activation/rollback; production maintenance requires explicit approval.",
    }
    return report, {
        "generated_at_utc": report["checked_at_utc"],
        "selected_platform_config_source_paths": [str(p) for p in selected],
        "backed_up_platform_config_info": backup,
        "production_service_inventory": units,
        "docker_metadata_scope": current,
        "verification_note": metadata,
        "public": report,
    }


def atomic_json(path, obj, mode):
    if path.is_symlink() or not path.parent.is_dir():
        raise NotReady("unsafe cutover report destination")
    fd, temp = tempfile.mkstemp(prefix=".osd-cutover-plan-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(obj, out, sort_keys=True, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        Path(temp).unlink(missing_ok=True)


def main():
    if os.geteuid() != 0:
        raise NotReady("requires read-only privileged service metadata")
    public, private = assess()
    atomic_json(PRIVATE, private, 0o600)
    atomic_json(PUBLIC, public, 0o644)
    print(json.dumps(public, sort_keys=True))


if __name__ == "__main__":
    main()
