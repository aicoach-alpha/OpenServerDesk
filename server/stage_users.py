"""Staging-only multi-actor capability registry, no production identities.

Per-user independent random tokens are stored only as salted PBKDF2 hashes.
API authorization is role based and fail-closed. Stage user data is never
combined with CasaOS account DB, Nextcloud or any external disk.
"""
from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path("/opt/openserverdesk-dev/runtime-stage/stage-users")
DATABASE = ROOT / "identities.json"
LOCK = ROOT / ".identities.lock"
ACTIVATION = Path("/opt/openserverdesk-dev/runtime-stage/.enable-stage-multiuser")
ACTIVATION_STRING = "OSD_STAGE_MULTIUSER_V1\n"
USER = re.compile(r"[a-z][a-z0-9_-]{2,30}\Z")
TOKEN = re.compile(r"[0-9a-f]{64}\Z")
ROLES = {"administrator", "operator", "reader"}
ACTION = {
    "read": ROLES,
    "write": {"administrator", "operator"},
    "admin": {"administrator"},
}
KDF_ROUNDS = 300_000
MAX_USERS = 12


class IdentityError(Exception):
    def __init__(self, code, status=403):
        self.code, self.status = code, status
        super().__init__(code)


def enabled():
    try:
        st = ACTIVATION.lstat()
        return (stat.S_ISREG(st.st_mode) and st.st_uid == 0
                and not st.st_mode & 0o022
                and ACTIVATION.read_text() == ACTIVATION_STRING)
    except (OSError, UnicodeError):
        return False


def setup_root(path=None):
    path = ROOT if path is None else Path(path)
    if path.is_symlink() or not path.is_dir() or path.stat().st_mode & 0o077:
        raise IdentityError("untrusted_staging_user_directory",503)
    if path.stat().st_uid != os.geteuid():
        raise IdentityError("staging_user_owner_mismatch",503)
    return path


@contextmanager
def locked(*, write=False):
    setup_root()
    if LOCK.is_symlink():
        raise IdentityError("unsafe_identity_lock",503)
    # Runtime web authentication is READ-ONLY in its strict systemd sandbox.
    # Staging account provisioning uses the separately controlled admin CLI.
    try:
        flags = os.O_RDWR | os.O_CREAT if write else os.O_RDONLY
        fd=os.open(LOCK,flags|os.O_NOFOLLOW,0o600)
    except OSError:
        raise IdentityError("identity_lock_unavailable",503)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX if write else fcntl.LOCK_SH)
        yield
    finally:
        fcntl.flock(fd,fcntl.LOCK_UN)
        os.close(fd)


def read():
    setup_root()
    if not DATABASE.is_file() or DATABASE.is_symlink():
        raise IdentityError("identity_store_not_initialized",503)
    st = DATABASE.stat()
    if (not stat.S_ISREG(st.st_mode) or st.st_mode & 0o077
            or st.st_size > 30_000):
        raise IdentityError("unsafe_identity_store",503)
    try:
        db=json.loads(DATABASE.read_text())
        if not isinstance(db,dict) or set(db) != {"version","users"} or db["version"]!=1:
            raise ValueError("invalid database version")
        users=db["users"]
        if not isinstance(users,dict) or len(users)>MAX_USERS:
            raise ValueError("invalid user count")
        for username,item in users.items():
            if (not USER.fullmatch(username) or not isinstance(item,dict)
                    or set(item)!={"role","salt","hash","disabled"}
                    or item["role"] not in ROLES
                    or not isinstance(item["disabled"],bool)
                    or not isinstance(item["salt"],str) or len(item["salt"])!=32
                    or not isinstance(item["hash"],str) or len(item["hash"])!=64
                    or not all(c in "0123456789abcdef" for c in item["salt"]+item["hash"])):
                raise ValueError("unsafe user row")
        return db
    except (ValueError,UnicodeError,TypeError,OSError):
        raise IdentityError("identity_store_corrupt",503)


def save(db):
    setup_root()
    if DATABASE.is_symlink():
        raise IdentityError("unsafe_identity_destination",503)
    fd,temp=tempfile.mkstemp(prefix=".identity-",dir=ROOT)
    try:
        with os.fdopen(fd,"w") as out:
            json.dump(db,out,sort_keys=True)
            out.write("\n")
            out.flush();os.fsync(out.fileno())
        os.chmod(temp,0o600)
        os.replace(temp,DATABASE)
        directory=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        Path(temp).unlink(missing_ok=True)


def digest(token,salt):
    return hashlib.pbkdf2_hmac("sha256",bytes.fromhex(token),
                              bytes.fromhex(salt),KDF_ROUNDS).hex()


def create(username,role,*, token=None):
    if not isinstance(username,str) or not USER.fullmatch(username) or role not in ROLES:
        raise IdentityError("invalid_stage_identity",400)
    token=token or secrets.token_hex(32)
    if not TOKEN.fullmatch(token):
        raise IdentityError("invalid_stage_token",400)
    with locked(write=True):
        if DATABASE.exists():
            db=read()
        else:
            db={"version":1,"users":{}}
        if username in db["users"] or len(db["users"])>=MAX_USERS:
            raise IdentityError("identity_exists_or_limit",409)
        if not db["users"] and role!="administrator":
            raise IdentityError("first_identity_must_be_admin",403)
        salt=secrets.token_hex(16)
        db["users"][username]={"role":role,"salt":salt,"hash":digest(token,salt),
                               "disabled":False}
        save(db)
    return token


def authorize(value,action):
    if not enabled():
        raise IdentityError("stage_multiuser_disabled",503)
    if action not in ACTION:
        raise IdentityError("unrecognized_permission",400)
    if not isinstance(value,str) or not value.startswith("Bearer "):
        raise IdentityError("authorization_required",401)
    supplied=value[7:]
    if not TOKEN.fullmatch(supplied):
        raise IdentityError("invalid_credential",401)
    # Never select a role by a caller-provided username. Match all hashes
    # in constant-time; permissions derive only from the stored identity.
    with locked():
        db=read()
        result=None
        for username,entry in sorted(db["users"].items()):
            valid=hmac.compare_digest(digest(supplied,entry["salt"]),entry["hash"])
            if valid and not entry["disabled"]:
                result=(username,entry["role"])
    if result is None:
        raise IdentityError("invalid_credential",401)
    if result[1] not in ACTION[action]:
        raise IdentityError("insufficient_permission",403)
    return {"actor":result[0],"role":result[1],
            "permissions":sorted(k for k,roles in ACTION.items() if result[1] in roles)}


def revoke(username):
    if not isinstance(username,str) or not USER.fullmatch(username):
        raise IdentityError("invalid_identity",400)
    with locked(write=True):
        db=read()
        if username not in db["users"]:
            raise IdentityError("identity_unknown",404)
        if db["users"][username]["role"]=="administrator" and not db["users"][username]["disabled"]:
            live=sum(not item["disabled"] and item["role"]=="administrator" for item in db["users"].values())
            if live<=1:
                raise IdentityError("cannot_disable_last_admin",409)
        db["users"][username]["disabled"]=True
        save(db)
