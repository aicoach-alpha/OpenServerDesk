#!/usr/bin/env python3
"""CasaOS CONFIG-ONLY recovery: independent SSD, original apps untouched.

Never reads, stats, opens, hashes or copies Nextcloud upload directories or
external HDD user content. Docker is queried for metadata only. Production
services and mounts are never changed. Restore is to a NEW staging directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import stat
import tempfile
from pathlib import Path
from urllib.parse import quote

from m1_platform_scope import protected, select

SSD = Path("/mnt/ssd-turbo")
BACKUP_ROOT = SSD / "openserverdesk-m1-platform-config-backups"
ID_PREFIX = "config-"
DB_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}
TRANSIENT_DB_SUFFIXES = ("-wal", "-shm", "-journal")
CAP_BYTES = 1024 ** 3
CAP_ITEMS = 100000


class Rejected(RuntimeError):
    pass


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def syncdir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def validate_source(path: Path):
    if protected(path) or not path.is_absolute() or path == Path("/"):
        raise Rejected("protected or non-platform source")
    if path.is_symlink() or not (path.is_dir() or path.is_file()):
        raise Rejected("invalid platform root")
    # Reject mounted subtrees before entering a directory; never walk mounts
    # belonging to an app or user data volume.
    if path.is_dir():
        prefix = str(path).rstrip("/") + "/"
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            columns = line.split()
            if len(columns) > 4:
                where = columns[4].replace(r"\040", " ")
                if where.startswith(prefix):
                    raise Rejected("nested mount inside platform source")
    return path


def check_target(source_paths: list[Path], *, fixture=False, root=BACKUP_ROOT):
    if not fixture:
        if root != BACKUP_ROOT or root.is_symlink():
            raise Rejected("backup target must be dedicated SSD location")
        if not SSD.is_mount() or SSD.is_symlink() or not SSD.is_dir():
            raise Rejected("separate SSD mount missing")
        devices = {p.lstat().st_dev for p in source_paths}
        if SSD.stat().st_dev in devices:
            raise Rejected("SSD must be separate filesystem from all platform sources")
    if root.is_symlink():
        raise Rejected("symlink backup root")
    root.mkdir(mode=0o700, parents=False, exist_ok=True)
    if root.stat().st_mode & 0o077:
        raise Rejected("backup directory must be root-private")
    if root.stat().st_uid != os.geteuid():
        raise Rejected("backup directory owner mismatch")
    if shutil.disk_usage(root).free < 512 * 1024 * 1024 and not fixture:
        raise Rejected("insufficient SSD headroom")
    return root


def safe_parts(sources: list[str]):
    selected = sorted({Path(x) for x in sources}, key=lambda p: (len(p.parts), str(p)))
    final = []
    for src in selected:
        validate_source(src)
        # Deduplicate nested Compose files already backed up with their
        # /var/lib/casaos config parent.
        if any(root == src or root in src.parents for root in final):
            continue
        final.append(src)
    return final


def is_db(path: Path) -> bool:
    return path.suffix.lower() in DB_EXTENSIONS


def transient(path: Path) -> bool:
    return path.name.endswith(TRANSIENT_DB_SUFFIXES)


def walk_paths(root: Path):
    if root.is_file():
        yield root
        return
    yield root
    for folder, dirs, names in os.walk(root, followlinks=False):
        f = Path(folder)
        for name in sorted(dirs + names):
            yield f / name
        dirs[:] = [name for name in dirs if not (f / name).is_symlink()]


def clone(src: Path, dest: Path, records: dict, data: Path, counters: dict):
    # Walk only explicitly selected platform sources after mount check.
    for item in walk_paths(src):
        st = item.lstat()
        relative = item.relative_to(src)
        dst = dest / relative
        key = str(dst.relative_to(data))
        if stat.S_ISDIR(st.st_mode):
            dst.mkdir(parents=True, exist_ok=True)
            os.chmod(dst, stat.S_IMODE(st.st_mode))
            os.chown(dst, st.st_uid, st.st_gid)
            records[key] = {"type": "dir", "mode": stat.S_IMODE(st.st_mode),
                            "uid": st.st_uid, "gid": st.st_gid}
        elif stat.S_ISLNK(st.st_mode):
            # Only read the link text. NEVER dereference or copy target.
            target = os.readlink(item)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.symlink_to(target)
            records[key] = {"type": "link", "target": target}
        elif stat.S_ISREG(st.st_mode):
            if transient(item):
                if not any((item.parent / item.name.removesuffix(end)).is_file()
                           for end in TRANSIENT_DB_SUFFIXES if item.name.endswith(end)):
                    raise Rejected("unrecognized SQLite transient file")
                continue
            counters["items"] += 1
            counters["bytes"] += st.st_size
            if counters["items"] > CAP_ITEMS or counters["bytes"] > CAP_BYTES:
                raise Rejected("platform configuration exceeds fixed size limits")
            dst.parent.mkdir(parents=True, exist_ok=True)
            if is_db(item):
                # SQLite online hot-backup gets a transactionally consistent
                # snapshot of THIS DB, not the whole cluster.
                uri = "file:" + quote(str(item), safe="/") + "?mode=ro"
                with sqlite3.connect(uri, uri=True, timeout=10) as original:
                    with sqlite3.connect(dst, timeout=10) as copied:
                        original.backup(copied)
                        if copied.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                            raise Rejected("inconsistent SQLite backup")
                kind = "sqlite"
            else:
                initial = sha(item)
                shutil.copyfile(item, dst, follow_symlinks=False)
                if sha(item) != initial or sha(dst) != initial:
                    raise Rejected("live configuration file changed during backup")
                kind = "file"
            os.chown(dst, st.st_uid, st.st_gid)
            os.chmod(dst, stat.S_IMODE(st.st_mode))
            records[key] = {
                "type": kind, "size": dst.stat().st_size,
                "sha256": sha(dst), "mode": stat.S_IMODE(st.st_mode),
                "uid": st.st_uid, "gid": st.st_gid,
            }
        else:
            raise Rejected("unsupported special platform configuration file")


def verify_tree(data: Path, manifest: dict) -> dict:
    if data.is_symlink() or not data.is_dir():
        raise Rejected("missing backup data root")
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise Rejected("invalid config backup format")
    records = manifest.get("entries")
    if not isinstance(records, dict) or not records:
        raise Rejected("missing configuration manifest")
    seen = set()
    for item in walk_paths(data):
        if item == data:
            continue
        key = str(item.relative_to(data))
        # No additional unmanifested sources allowed.
        if key not in records:
            raise Rejected("additional file in config backup")
        seen.add(key)
        entry = records[key]
        st = item.lstat()
        if entry["type"] == "dir":
            if (not stat.S_ISDIR(st.st_mode) or stat.S_IMODE(st.st_mode) != entry["mode"]
                    or st.st_uid != entry["uid"] or st.st_gid != entry["gid"]):
                raise Rejected("backup directory metadata differs")
        elif entry["type"] == "link":
            if not stat.S_ISLNK(st.st_mode) or os.readlink(item) != entry["target"]:
                raise Rejected("backup symlink changed")
        elif entry["type"] in ("file", "sqlite"):
            if (not stat.S_ISREG(st.st_mode) or st.st_size != entry["size"]
                    or sha(item) != entry["sha256"]
                    or stat.S_IMODE(st.st_mode) != entry["mode"]
                    or st.st_uid != entry["uid"] or st.st_gid != entry["gid"]):
                raise Rejected("backup checksum or ownership differs")
            if entry["type"] == "sqlite":
                with sqlite3.connect("file:"+quote(str(item), safe="/")+"?mode=ro",
                                     uri=True) as con:
                    if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise Rejected("restored SQLite integrity failed")
        else:
            raise Rejected("unknown entry")
    if set(records) != seen:
        raise Rejected("config backup is missing records")
    return {"files_verified":sum(e["type"] in ("file","sqlite") for e in records.values()),
            "sqlite_verified":sum(e["type"] == "sqlite" for e in records.values()),
            "symlinks_preserved":sum(e["type"] == "link" for e in records.values())}


def snapshot(*, fixture_sources=None, fixture_root=None):
    if os.geteuid() != 0:
        raise Rejected("config-only recovery requires root for owner fidelity")
    fixture = fixture_sources is not None
    if fixture:
        sources = safe_parts(fixture_sources)
        root = Path(fixture_root)
        if not root.name.startswith("config-only-fixture-"):
            raise Rejected("test fixture outside allowed namespace")
    else:
        inventory, found = select()
        if inventory["production_modified"] is not False:
            raise Rejected("source metadata invalid")
        sources = safe_parts(found)
        root = BACKUP_ROOT
    check_target(sources, fixture=fixture, root=root)
    candidate = root / ("config-" + secrets.token_hex(8))
    preparing = Path(tempfile.mkdtemp(prefix=".prepare-config-", dir=root))
    try:
        data = preparing / "data"
        data.mkdir(mode=0o700)
        manifest = {
            "version": 1, "scope": "CASAOS_PLATFORM_CONFIG_ONLY",
            "user_data_copied": False, "production_modified": False,
            "online_sqlite_individual_snapshot_not_global_atomicity": True,
            "entries": {},
        }
        counts = {"items":0,"bytes":0}
        for src in sources:
            dest = data / src.relative_to("/")
            # The staging layout reproduces absolute platform config paths
            # under data/. Every synthetic ancestor must be manifest-listed.
            for parent in reversed(tuple(
                    x for x in dest.parents if x != data and x.is_relative_to(data))):
                parent.mkdir(parents=True, exist_ok=True)
                key = str(parent.relative_to(data))
                manifest["entries"].setdefault(key, {
                     "type": "dir", "mode": stat.S_IMODE(parent.stat().st_mode),
                    "uid": parent.stat().st_uid, "gid": parent.stat().st_gid,
                })
            clone(src, dest, manifest["entries"], data, counts)
        proof = verify_tree(data, manifest)
        document = preparing / "manifest.json"
        with document.open("x") as stream:
            json.dump(manifest, stream, sort_keys=True)
            stream.flush();os.fsync(stream.fileno())
        syncdir(preparing)
        os.replace(preparing, candidate)
        syncdir(root)
        return {"backup_id":candidate.name, "selected_sources":len(sources),
                **proof, "manifest_sha256":sha(candidate/"manifest.json"),
                "user_data_copied":False,"production_modified":False,
                "backup_device_is_ssd":not fixture,
                "application_consistent_cluster_snapshot":False}
    finally:
        if preparing.exists():
            shutil.rmtree(preparing)


def verify(backup_id: str, *, root=BACKUP_ROOT):
    if not backup_id.startswith("config-") or not all(
        c in "0123456789abcdef" for c in backup_id[len("config-"):]) or len(backup_id) != 23:
        raise Rejected("invalid backup identifier")
    folder = Path(root) / backup_id
    if folder.is_symlink() or not folder.is_dir():
        raise Rejected("unknown backup")
    document = folder / "manifest.json"
    if document.is_symlink() or document.stat().st_size > 10_000_000:
        raise Rejected("invalid backup manifest")
    manifest = json.loads(document.read_text())
    if manifest.get("scope") != "CASAOS_PLATFORM_CONFIG_ONLY" or manifest.get("user_data_copied") is not False:
        raise Rejected("untrusted backup scope")
    return manifest, verify_tree(folder / "data", manifest)


def restore(backup_id: str, *, root=BACKUP_ROOT):
    if os.geteuid() != 0:
        raise Rejected("staging restore requires owner fidelity")
    manifest, counts = verify(backup_id, root=root)
    root = Path(root)
    if root.is_symlink() or root.stat().st_mode & 0o077:
        raise Rejected("unsafe restore root")
    recovered = root / "restored"
    recovered.mkdir(mode=0o700, exist_ok=True)
    if recovered.is_symlink() or recovered.stat().st_mode & 0o077:
        raise Rejected("unsafe restored directory")
    target = recovered / backup_id
    if target.exists() or target.is_symlink():
        raise Rejected("existing recovery cannot be overwritten")
    preparing = Path(tempfile.mkdtemp(prefix=".restore-config-", dir=recovered))
    try:
        shutil.copytree(root / backup_id / "data", preparing / "data",
                        symlinks=True, copy_function=shutil.copy2)
        # shutil.copy2 preserves file modes but NOT Unix ownership. Reapply
        # only the already-verified manifest's UID/GID to the new staging
        # tree. Never apply ownership to the original source or HDD.
        for name, entry in manifest["entries"].items():
            if entry["type"] not in ("dir", "file", "sqlite"):
                continue
            target_item = preparing / "data" / name
            if target_item.is_symlink():
                raise Rejected("unexpected staged symlink")
            os.chown(target_item, entry["uid"], entry["gid"], follow_symlinks=False)
        verify_tree(preparing / "data", manifest)
        os.replace(preparing / "data", target)
        syncdir(recovered)
        return {"restored_path_kind":"new_private_ssd_staging_tree",
                "backup_id":backup_id, **counts,
                "user_data_copied":False,"production_modified":False,
                "original_platform_config_overwritten":False}
    finally:
        if preparing.exists():
            shutil.rmtree(preparing)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("action", choices=["backup","verify","restore"])
    p.add_argument("--backup-id", default=None)
    args=p.parse_args()
    if args.action=="backup":
        result=snapshot()
    elif args.action=="verify":
        _m,result=verify(args.backup_id or "")
    else:
        result=restore(args.backup_id or "")
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
