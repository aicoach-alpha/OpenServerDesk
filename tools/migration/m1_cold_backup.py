#!/usr/bin/env python3
"""Scoped CasaOS platform config backup; NEVER Nextcloud user data.

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


def _paths_fresh(*, fixture_mode=False):
    if not fixture_mode:
        # The live scope is platform configuration only. Existing Docker
        # bind mounts are preserved as references; user files are not copied.
        # Do not call collect(): it stats EVERY original bind including
        # external Nextcloud user data which is outside migration scope.
        from m1_platform_scope import select
        return select()
    # Fixture-only compatibility, no production path supplied by caller.
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


def _independent_disk(destination, sources):
    # A backup on ANY filesystem that holds original source data is not
    # independently recoverable if that source disk fails.
    if destination.is_symlink() or not destination.is_dir():
        return False
    return destination.stat().st_dev not in {
        os.stat(path).st_dev for path in sources
    }


def plan(*, fixture_mode=False):
    report, files = _paths_fresh(fixture_mode=fixture_mode)
    independent = _independent_disk(BACKUPS, files)
    return {
        "plan_format": LABEL,
        "analyzed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "container_count": report["container_count"],
        "running_containers": report["running_container_count"],
        "writable_live_mounts": report["live_writable_mount_count"],
        "compose_project_count": report["compose_project_count"],
        "bind_source_count": report["unique_bind_source_count"],
        "additional_compose_sources": (
            len(files)-report["unique_bind_source_count"] if fixture_mode
            else None),
        "selected_platform_config_sources": len(files),
        "protected_bind_references_skipped": report.get("protected_bind_references_skipped", 0),
        "total_unique_backup_sources": len(files),
        "backup_scope": "platform_configs_only_no_external_user_uploads",
        "external_user_data_copied": False,
        "independent_backup_destination": independent,
        "cold_backup_authorized": (report["running_container_count"] == 0 and
                                   report["live_writable_mount_count"] == 0 and
                                   (independent or fixture_mode)),
        "production_modified": False,
        "actual_sources_excluded_from_public_report": True,
    }


def _syncdir(folder):
    fd = os.open(folder, os.O_DIRECTORY | os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def _entry_metadata(node):
    """Fingerprint ALL recoverable metadata including ACL-backed xattrs."""
    st = node.lstat()
    if stat.S_ISREG(st.st_mode):
        out = {"type": "file", "size": st.st_size, "sha256": _sha256(node)}
    elif stat.S_ISDIR(st.st_mode):
        out = {"type": "directory"}
    elif stat.S_ISLNK(st.st_mode):
        out = {"type": "symlink", "target": os.readlink(node)}
    else:
        raise BackupRejected("special file is not recoverable")
    out.update(mode=stat.S_IMODE(st.st_mode), uid=st.st_uid,
               gid=st.st_gid, mtime_ns=st.st_mtime_ns)
    try:
        out["xattrs_sha256"] = {
            name: hashlib.sha256(os.getxattr(
                node, name, follow_symlinks=False)).hexdigest()
            for name in sorted(os.listxattr(node, follow_symlinks=False))
        }
    except OSError as exc:
        raise BackupRejected("cannot verify source ACL and xattrs") from exc
    return out


def _tree_rows(root, data_root):
    if root.is_symlink() or not (root.is_file() or root.is_dir()):
        raise BackupRejected("unsafe backup source root")
    nodes = [root]
    if root.is_dir():
        nodes.extend(sorted(root.rglob("*")))
    if len(nodes) > 100000:
        raise BackupRejected("too many files in one backup source")
    # A link to an inode OUTSIDE this tree cannot be reconstructed as a
    # self-contained recovery source. cp -a should preserve internal links.
    hardlinks = {}
    for node in nodes:
        st = node.lstat()
        if stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
            key = (st.st_dev, st.st_ino)
            hardlinks.setdefault(key, {"expected": st.st_nlink, "nodes": []})["nodes"].append(node)
    identity = {}
    for entry in hardlinks.values():
        if len(entry["nodes"]) != entry["expected"]:
            raise BackupRejected("hardlink crosses backup source boundary")
        first = min(str(x.relative_to(root)) for x in entry["nodes"])
        for node in entry["nodes"]:
            identity[node] = first
    result = []
    for node in nodes:
        row = {"rel": str(node.relative_to(data_root))}
        row.update(_entry_metadata(node))
        row["hardlink_ref"] = identity.get(node)
        if row["type"] == "symlink":
            if os.path.isabs(row["target"]):
                raise BackupRejected("absolute symlink requires separate recovery plan")
            resolved = (node.parent / row["target"]).resolve(strict=False)
            if not resolved.is_relative_to(root.resolve(strict=True)):
                raise BackupRejected("backup symlink escapes its source tree")
        result.append(row)
    return result


def _same_source_data(before, copied):
    # Both enumerations use different generated source-root directory names.
    # Remove exactly the first path component and compare ALL remaining
    # data and metadata for a byte-for-byte, metadata-for-metadata copy.
    def relative(rows):
        result = []
        for item in rows:
            first, sep, rest = item["rel"].partition("/")
            result.append({**item, "rel": rest if sep else "."})
        return result
    return relative(before) == relative(copied)


def cold_backup(*, fixture_mode=False):
    if os.geteuid() != 0:
        raise BackupRejected("cold backup requires dedicated privileged operator")
    report, files = _paths_fresh(fixture_mode=fixture_mode)
    # Require ALL original Docker writers (including unexpected read-only
    # mounts) to be stopped. No automatic downtime or stop/restart action.
    if report["running_container_count"] or report["live_writable_mount_count"]:
        raise BackupRejected("COLD_BACKUP_BLOCKED_RUNNING_PRODUCTION_APPS")
    _safe_dir(STAGE)
    _safe_dir(BACKUPS, STAGE)
    if BACKUPS.stat().st_mode & 0o077:
        raise BackupRejected("backup storage must be root private 0700")
    if not fixture_mode and not _independent_disk(BACKUPS, files):
        raise BackupRejected("INDEPENDENT_BACKUP_TARGET_REQUIRED")
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
            # Validate input tree BEFORE copy; do not treat missing ACLs,
            # external symlinks or unsupported special files as a success.
            before = _tree_rows(path, path.parent)
            # cp -a preserves owners, timestamps, hardlinks within each
            # source, ACLs and xattrs; we verify that assumption explicitly.
            _run("cp", "-a", "--no-target-directory", "--", str(path), str(dst),
                 timeout=300)
            if not dst.exists() and not dst.is_symlink():
                raise BackupRejected("copy missing from backup tree")
            rows = _tree_rows(dst, data)
            if not _same_source_data(before, rows):
                raise BackupRejected("backup lost data or filesystem metadata")
            if _tree_rows(path, path.parent) != before:
                raise BackupRejected("source data modified while copying")
            if sum(len(x["items"]) for x in manifest["sources"]) + len(rows) > 100000:
                raise BackupRejected("excessive backup file entry count")
            manifest["sources"].append({"original_path":src, "copy_root":dirname,
                                        "items":rows})
        new_report, new_files = _paths_fresh(fixture_mode=fixture_mode)
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
    """Reconcile exact on-disk inventory against the complete manifest."""
    if data_root.is_symlink() or not data_root.is_dir():
        raise BackupRejected("unsafe backup data directory")
    if set(raw) != {"format", "created_at_utc", "sources",
                    "initial_live_container_count", "production_modified"}:
        raise BackupRejected("invalid backup schema")
    if raw["production_modified"] is not False or raw["initial_live_container_count"] != 0:
        raise BackupRejected("not a quiesced backup")
    entries = raw["sources"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= 10000:
        raise BackupRejected("invalid source list")
    listed = set()
    count = 0
    for source in entries:
        if not isinstance(source, dict) or set(source) != {
                "original_path", "copy_root", "items"}:
            raise BackupRejected("invalid manifest source")
        dirname = source["copy_root"]
        if not isinstance(dirname, str) or not re.fullmatch(r"source-\d{4}", dirname):
            raise BackupRejected("invalid source folder")
        if dirname in listed:
            raise BackupRejected("duplicate source record")
        listed.add(dirname)
        if not isinstance(source["items"], list):
            raise BackupRejected("invalid manifest items")
        actual = _tree_rows(data_root / dirname, data_root)
        if actual != source["items"]:
            raise BackupRejected("missing, extra, corrupted or metadata-altered files")
        count += len(actual)
        if count > 100000:
            raise BackupRejected("backup file count limit")
    if {p.name for p in data_root.iterdir()} != listed:
        raise BackupRejected("unlisted source in backup")
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


def restore_to_staging(name, *, fixture_mode=False):
    """Recovery rehearsal into a NEW root-private staging destination ONLY."""
    result = verify_bundle(name)
    _safe_dir(STAGE)
    _safe_dir(BACKUPS, STAGE)
    _safe_dir(RECOVERED, STAGE)
    if RECOVERED.stat().st_mode & 0o077:
        raise BackupRejected("recovery directory must be root private")
    if not fixture_mode:
        _report, actual_sources = _paths_fresh(fixture_mode=fixture_mode)
        if not _independent_disk(RECOVERED, actual_sources):
            raise BackupRejected("INDEPENDENT_RESTORE_TARGET_REQUIRED")
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
