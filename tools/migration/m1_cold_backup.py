#!/usr/bin/env python3
"""Actual full-CasaOS-appdata cold backup; production-safe fail-closed gating.

A fresh Docker inspection defines sources; callers cannot supply arbitrary
backup source paths. Real backup deliberately REFUSES while any Docker
workload is running. It never stops a container or modifies live source data.
All backup artifacts stay private in OpenServerDesk's staging filesystem.
No public HTTP endpoint calls this module. Not a final cutover controller.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m1_app_data_inventory import collect

STAGE = Path("/opt/openserverdesk-dev/runtime-stage")
BACKUPS = STAGE / "cold-backups"
RECOVERED = STAGE / "cold-recovery"
MANIFEST = "manifest.json"
LABEL = "OSD_CASAOS_COLD_BACKUP_V1"
ID_PATTERN = re.compile(r"backup-[0-9a-f]{12}\Z")


class BackupRejected(RuntimeError):
    pass


def _sha256(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_dir(path: Path, parent: Path | None = None):
    if path.is_symlink() or not path.is_dir():
        raise BackupRejected("missing or symlinked backup storage")
    if parent is not None and path.resolve(strict=True).parent != parent.resolve(strict=True):
        raise BackupRejected("backup directory outside dedicated storage")


def _run(*argv, timeout=180):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise BackupRejected("filesystem copy tool failed or timed out")
    if p.returncode:
        raise BackupRejected("filesystem copy tool failed")
    return p.stdout


def _mountpoints():
    """Filesystem mountpoints used only to reject unrepresented nested mounts."""
    points = set()
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        cols = line.split()
        if len(cols) > 4:
            # mountinfo escapes spaces and backslash as octal.
            raw = cols[4]
            points.add(re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), raw))
    return points


def _paths_fresh():
    report = collect()
    if report.get("production_modified") is not False:
        raise BackupRejected("unexpected inventory schema")
    binds = report.get("bind_sources")
    if not isinstance(binds, dict) or not binds:
        raise BackupRejected("no bind-mount inventory")
    sources = set(binds)
    composed = {
        file_info["path"]
        for p in report["compose_projects"].values()
        for file_info in p.get("file_status", [])
        if file_info.get("exists") and not file_info.get("symlink")
    }
    expected_compose_count = sum(len(p.get("file_status", []))
                                 for p in report["compose_projects"].values())
    if len(composed) != expected_compose_count:
        raise BackupRejected("a Compose config file is unavailable/unsafe")
    files = sorted(sources | composed)
    if len(files) > 10000:
        raise BackupRejected("unexpected number of backup data sources")
    mounts = _mountpoints()
    for source in files:
        p = Path(source)
        if (not p.is_absolute() or ".." in p.parts or p.resolve() != p
                or p.is_symlink() or not p.exists()
                or not (p.is_file() or p.is_dir())
                or str(p) in ("/", "/etc", "/var", "/home", "/opt")):
            raise BackupRejected("unsafe external bind or Compose path")
        # A source with a nested mounted filesystem would otherwise produce
        # an apparently successful but incomplete backup via cp -a.
        if p.is_dir():
            prefix = str(p).rstrip("/") + "/"
            for mount in mounts:
                if mount.startswith(prefix) and mount not in sources:
                    raise BackupRejected("an unrepresented nested mount would be missed")
    return report, files


def plan():
    report, files = _paths_fresh()
    return {
        "plan_format": LABEL,
        "analyzed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "container_count": report["container_count"],
        "running_containers": report["running_container_count"],
        "writable_live_mounts": report["live_writable_mount_count"],
        "compose_project_count": report["compose_project_count"],
        "bind_source_count": report["unique_bind_source_count"],
        "additional_compose_sources": len(files)-report["unique_bind_source_count"],
        "total_unique_backup_sources": len(files),
        "cold_backup_authorized": (report["running_container_count"] == 0 and
                                   report["live_writable_mount_count"] == 0),
        "production_modified": False,
        "actual_sources_excluded_from_public_report": True,
    }


def _syncdir(folder):
    fd = os.open(folder, os.O_DIRECTORY | os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def cold_backup():
    if os.geteuid() != 0:
        raise BackupRejected("cold backup requires dedicated privileged operator")
    report, files = _paths_fresh()
    # Require ALL original Docker writers (including unexpected read-only
    # mounts) to be stopped. No automatic downtime or stop/restart action.
    if report["running_container_count"] or report["live_writable_mount_count"]:
        raise BackupRejected("COLD_BACKUP_BLOCKED_RUNNING_PRODUCTION_APPS")
    _safe_dir(STAGE)
    _safe_dir(BACKUPS, STAGE)
    if BACKUPS.stat().st_mode & 0o077:
        raise BackupRejected("backup storage must be root private 0700")
    # Preflight dry-run disk estimate; refuse when unknown, too large or
    # insufficient. du can be slow on huge production trees, so fail closed.
    unique_sources = [Path(x) for x in files]
    estimated = 0
    for source in unique_sources:
        size = _run("du", "--bytes", "--summarize", "--", str(source), timeout=60)
        try:
            estimated += int(size.split("\t",1)[0])
        except (ValueError, IndexError):
            raise BackupRejected("unable to measure source bytes")
    free = shutil.disk_usage(BACKUPS).free
    if estimated >= int(free * 0.80):
        raise BackupRejected("insufficient free capacity for full cold backup")
    owner = "backup-" + os.urandom(6).hex()
    preparing = Path(tempfile.mkdtemp(prefix=".cold-preparing-", dir=BACKUPS))
    os.chmod(preparing, 0o700)
    try:
        manifest = {
            "format": LABEL,
            "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "sources": [],
            "initial_live_container_count": report["running_container_count"],
            "production_modified": False,
        }
        data = preparing / "data"
        data.mkdir(mode=0o700)
        for index, src in enumerate(files):
            path = Path(src)
            dirname = f"source-{index:04d}"
            dst = data / dirname
            # cp -a preserves symlinks, owner, permissions, timestamps,
            # hard links *within one source*, extended attributes and ACLs.
            _run("cp", "-a", "--no-target-directory", "--", str(path), str(dst),
                 timeout=300)
            if not dst.exists() and not dst.is_symlink():
                raise BackupRejected("copy missing from backup tree")
            rows = []
            for sub in [dst, *sorted(dst.rglob("*"))] if dst.is_dir() else [dst]:
                st = sub.lstat()
                if not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)
                        or stat.S_ISLNK(st.st_mode)):
                    raise BackupRejected("unsupported special file in backup")
                rel = str(sub.relative_to(data))
                if stat.S_ISREG(st.st_mode):
                    rows.append({"rel":rel, "type":"file", "sha256":_sha256(sub),
                                 "size":st.st_size})
                elif stat.S_ISLNK(st.st_mode):
                    rows.append({"rel":rel, "type":"symlink",
                                 "target":os.readlink(sub)})
                else:
                    rows.append({"rel":rel, "type":"directory"})
            if sum(len(x["items"]) for x in manifest["sources"]) + len(rows) > 100000:
                raise BackupRejected("excessive backup file entry count")
            manifest["sources"].append({"original_path":src, "copy_root":dirname,
                                        "items":rows})
        new_report, new_files = _paths_fresh()
        if (new_files != files or new_report["running_container_count"]
                or new_report["live_writable_mount_count"]
                or new_report["container_count"] != report["container_count"]):
            raise BackupRejected("Docker app state changed during cold backup")
        document = preparing / MANIFEST
        with document.open("x") as handle:
            json.dump(manifest, handle, sort_keys=True)
            handle.flush(); os.fsync(handle.fileno())
        _syncdir(preparing)
        os.rename(preparing, BACKUPS / owner)
        _syncdir(BACKUPS)
        return {
            "id":owner, "sources":len(files),
            "files":sum(len(x["items"]) for x in manifest["sources"]),
            "manifest_sha256":_sha256(BACKUPS / owner / MANIFEST),
            "no_production_mutation":True,
            "data_consistency": "cold_docker_quiesced_not_independently_verified",
        }
    finally:
        if preparing.exists():
            shutil.rmtree(preparing)


def _check_manifest_tree(data_root, raw):
    count=0
    for source in raw["sources"]:
        dirname=source.get("copy_root")
        if not re.fullmatch(r"source-\d{4}",str(dirname)):
            raise BackupRejected("invalid backup source")
        if not isinstance(source.get("items"), list):
            raise BackupRejected("invalid backup manifest item list")
        for item in source["items"]:
            relative = Path(item["rel"])
            if (relative.is_absolute() or ".." in relative.parts
                    or relative.parts[0] != dirname):
                raise BackupRejected("unsafe archive path")
            p = data_root / relative
            if not p.is_relative_to(data_root):
                raise BackupRejected("unsafe archive path")
            current = p.parent
            while current != data_root:
                if current.is_symlink():
                    raise BackupRejected("unsafe symlinked archive parent")
                current = current.parent
            if item["type"] == "file":
                if p.is_symlink() or _sha256(p) != item["sha256"] or p.stat().st_size != item["size"]:
                    raise BackupRejected("backup hash mismatch")
            elif item["type"] == "symlink":
                if not p.is_symlink() or os.readlink(p) != item["target"]:
                    raise BackupRejected("backup symlink mismatch")
            elif item["type"] == "directory":
                if p.is_symlink() or not p.is_dir():
                    raise BackupRejected("backup directory mismatch")
            else:
                raise BackupRejected("unsupported backup entry")
            count+=1
    return count


def verify_bundle(name):
    if not ID_PATTERN.fullmatch(name):
        raise BackupRejected("invalid bundle id")
    _safe_dir(STAGE)
    _safe_dir(BACKUPS, STAGE)
    folder = BACKUPS / name
    _safe_dir(folder, BACKUPS)
    doc = folder / MANIFEST
    if doc.is_symlink() or doc.stat().st_size > 10_000_000:
        raise BackupRejected("unsafe backup manifest")
    raw = json.loads(doc.read_text())
    if raw.get("format") != LABEL or not isinstance(raw.get("sources"),list):
        raise BackupRejected("invalid backup manifest")
    count = _check_manifest_tree(folder / "data", raw)
    return {"bundle":name,"verified_items":count,
            "verified_sources":len(raw["sources"]),
            "manifest_sha256":_sha256(doc),
            "production_modified":False}


def restore_to_staging(name):
    """Recovery rehearsal into a NEW root-private staging destination ONLY."""
    result = verify_bundle(name)
    _safe_dir(STAGE)
    _safe_dir(BACKUPS, STAGE)
    _safe_dir(RECOVERED, STAGE)
    if RECOVERED.stat().st_mode & 0o077:
        raise BackupRejected("recovery directory must be root private")
    dest = RECOVERED / name
    if dest.exists() or dest.is_symlink():
        raise BackupRejected("existing recovery directory cannot be overwritten")
    source = BACKUPS / name
    manifest = json.loads((source / MANIFEST).read_text())
    preparing = Path(tempfile.mkdtemp(prefix=".restore-preparing-", dir=RECOVERED))
    os.chmod(preparing, 0o700)
    try:
        _run("cp", "-a", "--no-target-directory", "--",
             str(source / "data"), str(preparing / "data"), timeout=300)
        # Post-copy verification BEFORE atomic publication.
        restored = _check_manifest_tree(preparing / "data", manifest)
        if restored != result["verified_items"]:
            raise BackupRejected("recovered data item count mismatch")
        _syncdir(preparing)
        os.replace(preparing, dest)
        _syncdir(RECOVERED)
        return {"restored_bundle": name,
                "restored_items_verified": restored,
                "restored_sources":result["verified_sources"],
                "recovery_destination":"private_staging_only",
                "production_modified":False}
    finally:
        if preparing.exists():
            shutil.rmtree(preparing)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("action", choices=("plan","backup","verify","restore"))
    parser.add_argument("--bundle")
    args=parser.parse_args()
    try:
        if args.action=="plan": result=plan()
        elif args.action=="backup": result=cold_backup()
        elif args.action=="verify": result=verify_bundle(args.bundle or "")
        else: result=restore_to_staging(args.bundle or "")
        print(json.dumps(result, sort_keys=True))
    except (BackupRejected, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status":"blocked",
                          "reason":str(exc)[:140],
                          "production_modified":False}),file=sys.stderr)
        sys.exit(2)

if __name__=="__main__":
    main()
