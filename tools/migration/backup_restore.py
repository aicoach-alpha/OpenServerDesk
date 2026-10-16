#!/usr/bin/env python3
"""CasaOS configuration backup with SQLite online backup and isolated restore rehearsal."""
import argparse, hashlib, json, os, shutil, sqlite3, tarfile, tempfile
from pathlib import Path
from m1_platform_scope import protected
SRC = [Path("/etc/casaos"), Path("/var/lib/casaos/apps"), Path("/usr/share/casaos")]
DB = Path("/var/lib/casaos/db")
DEST = Path("/var/backups/openserverdesk-migration")


def ensure_platform_tree_only(root):
    # Refuse nested mounts instead of traversing them into user-upload HDDs.
    if protected(root) or root.is_symlink():
        raise RuntimeError("unsafe or external platform config root")
    root_str = str(root).rstrip("/") + "/"
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        cols = line.split()
        if len(cols) < 5:
            continue
        mount = cols[4].replace(r" ", " ")
        if mount.startswith(root_str):
            raise RuntimeError("nested mount inside platform config scope")
    if root.is_dir():
        if root.stat().st_dev != root.parent.stat().st_dev:
            raise RuntimeError("platform root is an unexpected separate mount")
        return
    raise RuntimeError("platform config source unavailable")


def ensure_platform_database(path):
    if protected(path) or path.is_symlink() or not path.is_file():
        raise RuntimeError("invalid internal platform database")

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()
def backup():
    # No production or user-data source is accessed until every explicit
    # platform root and database parent passes the mount/symlink boundary.
    for src in SRC:
        ensure_platform_tree_only(src)
    ensure_platform_tree_only(DB)
    DEST.mkdir(mode=0o700,parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="osd-backup-") as t:
        root=Path(t)
        for src in SRC:
            if src.is_dir():
                target=root/src.relative_to("/")
                shutil.copytree(src,target,symlinks=True)
        for db in DB.glob("*.db"):
            ensure_platform_database(db)
            target=root/db.relative_to("/")
            target.parent.mkdir(parents=True,exist_ok=True)
            with sqlite3.connect(f"file:{db}?mode=ro",uri=True) as origin, sqlite3.connect(target) as out:
                origin.backup(out)
            with sqlite3.connect(target) as check:
                if check.execute("PRAGMA integrity_check").fetchone()[0]!="ok": raise RuntimeError("sqlite corrupt")
        manifest={str(p.relative_to(root)):digest(p) for p in root.rglob("*") if not p.is_symlink() and p.is_file()}
        (root/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2))
        fd,name=tempfile.mkstemp(prefix="casaos-config-",suffix=".tar.gz",dir=DEST)
        os.close(fd)
        result=Path(name)
        try:
            with tarfile.open(result,"w:gz",dereference=False) as tar:
                for p in sorted(root.rglob("*")):tar.add(p,arcname=str(p.relative_to(root)),recursive=False)
            os.chmod(result,0o600)
            return result
        except Exception:
            result.unlink(missing_ok=True)
            raise
def rehearse(archive):
    with tempfile.TemporaryDirectory(prefix="osd-restore-test-") as t:
        root=Path(t).resolve()
        with tarfile.open(archive,"r:gz") as tar:
            for member in tar.getmembers():
                target=(root/member.name).resolve()
                if not target.is_relative_to(root) or member.islnk() or not (member.isfile() or member.isdir() or member.issym()):
                    raise ValueError("unsafe archive member")
                if member.issym():
                    # Preserve only relative symlinks whose targets remain inside the staging tree.
                    if member.linkname.startswith("/") or not (target.parent/member.linkname).resolve().is_relative_to(root):
                        raise ValueError("unsafe symlink")
            tar.extractall(root,filter="data")
        manifest=json.loads((root/"manifest.json").read_text())
        if not isinstance(manifest,dict):
            raise ValueError("invalid backup manifest")
        actual={str(p.relative_to(root)) for p in root.rglob("*")
                if not p.is_symlink() and p.is_file() and p!=root/"manifest.json"}
        if set(manifest)!=actual:
            raise ValueError("backup manifest does not cover exactly the archived files")
        for path,checksum in manifest.items():
            rel=Path(path)
            if (not isinstance(path,str) or rel.is_absolute() or not path or
                    "." in rel.parts or ".." in rel.parts or
                    not isinstance(checksum,str) or len(checksum)!=64 or
                    any(ch not in "0123456789abcdef" for ch in checksum)):
                raise ValueError("invalid backup manifest entry")
            target=root/rel
            if target.is_symlink() or not target.resolve().is_relative_to(root):
                raise ValueError("unsafe backup manifest entry")
            if digest(target)!=checksum:raise RuntimeError(f"hash mismatch {path}")
        dbs=[root/path for path in manifest if path.endswith(".db") and root.joinpath(path).is_file()]
        for db in dbs:
            with sqlite3.connect(db) as con:
                if con.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise RuntimeError("invalid sqlite")
        return {"files_verified":len(manifest),"sqlite_verified":len(dbs),"external_hdd_copied":False,"production_modified":False}
if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=["backup","rehearse"])
    a.add_argument("--archive")
    args=a.parse_args()
    if args.action=="backup":
        archive=backup()
        print(json.dumps({"archive":str(archive),"sha256":digest(archive),"result":rehearse(archive)}))
    else:
        print(json.dumps(rehearse(Path(args.archive))))
