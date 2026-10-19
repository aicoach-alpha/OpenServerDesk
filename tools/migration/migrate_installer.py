#!/usr/bin/env python3
"""M1.4 in-place migration installer pre-activation gate. No production mutations."""
import argparse, hashlib, importlib.util, json, os, subprocess
from urllib.request import urlopen
from pathlib import Path
import migration_preflight as preflight
import backup_restore as backup
from m1_fixture_activation import execute as fixture_execute
from full_app_recovery import snapshot as app_snapshot, restore as app_restore, root_fixture, scan as app_scan, projects as app_projects, owner as app_owner, quiesced as app_quiesced

def sha256(p):
    return backup.digest(p)

def gate(archive, candidate=None):
    state=preflight.inspect()
    failures=[k for k,v in state["checks"].items() if not v]
    if not archive.is_file():
        failures.append("backup_missing")
    else:
        try:
            proof=backup.rehearse(archive)
            if proof["sqlite_verified"]<3:failures.append("incomplete_casaos_db_backup")
        except Exception as e:
            failures.append("backup_invalid:"+type(e).__name__)
            proof=None
    package=None
    if candidate:
        if not candidate.is_file() or candidate.suffix!=".deb":
            failures.append("candidate_missing_or_not_deb")
        else:
            info=subprocess.run(["dpkg-deb","--field",str(candidate),"Package","Version","Architecture"],
                                capture_output=True,text=True,timeout=10)
            if info.returncode:failures.append("invalid_deb")
            else:package={"metadata":info.stdout.strip(),"sha256":sha256(candidate)}
    else:
        failures.append("signed_candidate_not_provided")
    return {"step":"M1.4","mode":"non_mutating_staging_gate",
            "casaos_version":state["casaos_version"],
            "backup":str(archive),"backup_sha256":sha256(archive) if archive.is_file() else None,
            "restore_rehearsal":proof if archive.is_file() else None,
            "candidate":package,"checks":state["checks"],
            "failures":failures,"safe_to_activate":False,
            "activation_implemented":False,
            "rollback_implemented":False,
            "note":"Fails closed: requires signed candidate, isolated install rehearsal, and tested rollback before activation"}
def checkpoint_integrity(target, app_root):
    """Verify fixture manifests and content; never access live production paths."""
    from m1_fixture_activation import status as fixture_status
    from journaled_pair import digest as pair_digest
    target_status = fixture_status(target)
    target = Path(target).resolve()
    if target_status["state"] == "ROLLBACK_AVAILABLE":
        journal = target / ".osd-undo"
        try:
            manifest = json.loads((journal / "manifest.json").read_text())
            if set(manifest) != {"userservice", "user.db"}:
                raise ValueError("unexpected undo manifest")
            if (journal / "manifest.json").is_symlink() or any(
                   not isinstance(expected, str) or
                   (journal / name).is_symlink() or
                   pair_digest(journal / name) != expected
                   for name, expected in manifest.items()):
                raise ValueError("undo checksum mismatch")
            target_status["journal_integrity"] = "VERIFIED"
        except (OSError, ValueError, TypeError, KeyError):
            target_status["journal_integrity"] = "INVALID"
            target_status["activation_allowed"] = False
    root = root_fixture(app_root)
    bundle = root / "bundle"
    recovered = root / "recovered"
    app_state = "NO_SNAPSHOT"
    app_integrity = "NOT_AVAILABLE"
    if bundle.exists() or bundle.is_symlink():
        app_state = "SNAPSHOT_AVAILABLE"
        try:
            if bundle.is_symlink() or not bundle.is_dir():
                raise ValueError("invalid bundle")
            manifest_path = bundle / "manifest.json"
            if manifest_path.is_symlink():
                raise ValueError("symlinked manifest")
            doc = json.loads(manifest_path.read_text())
            if (set(doc) != {"format", "owner", "projects"} or doc["format"] != 1
                    or not isinstance(doc["projects"], dict) or not doc["projects"]
                    or doc["owner"] != app_owner(root)):
                raise ValueError("invalid or foreign manifest")
            entries = app_projects(bundle / "data")
            if {p.name: app_scan(p) for p in entries} != doc["projects"]:
                raise ValueError("snapshot checksum mismatch")
            app_integrity = "VERIFIED"
            if recovered.exists() or recovered.is_symlink():
                if recovered.is_symlink() or not recovered.is_dir():
                    raise ValueError("invalid recovered tree")
                restored = app_projects(recovered)
                if {p.name: app_scan(p) for p in restored} != doc["projects"]:
                    raise ValueError("recovery checksum mismatch")
                app_state = "RESTORED"
        except (OSError, ValueError, TypeError, KeyError):
            app_integrity = "INVALID"
    elif recovered.exists() or recovered.is_symlink():
        app_state = "ORPHAN_RECOVERY"
        app_integrity = "INVALID"
    return {"scope": "STAGING_FIXTURE_CHECKPOINT_ONLY",
            "service": target_status, "applications": app_state,
            "application_integrity": app_integrity,
            "migration_allowed": False, "production_modified": False}

def candidate_identity(candidate):
    """Read-only package identity tied to the exact staged .deb bytes."""
    candidate = Path(candidate)
    if candidate.is_symlink() or not candidate.is_file() or candidate.suffix != ".deb":
        raise ValueError("regular .deb candidate required")
    info = subprocess.run(
        ["dpkg-deb", "--field", str(candidate), "Package", "Version", "Architecture"],
        capture_output=True, text=True, timeout=10)
    if info.returncode:
        raise ValueError("invalid candidate package")
    fields = info.stdout.strip().splitlines()
    if len(fields) != 3 or fields[0] != "openserverdesk" or not all(fields):
        raise ValueError("unexpected candidate identity")
    return {"package": fields[0], "version": fields[1],
            "architecture": fields[2], "sha256": sha256(candidate)}


def verified_stage_release(candidate):
    """Bind a candidate to the existing staging Ed25519 manifest verifier."""
    signing = Path(__file__).resolve().parents[1] / "release/stage_artifact_signing_0651.py"
    spec = importlib.util.spec_from_file_location("osd_stage_signing", signing)
    if spec is None or spec.loader is None:
        raise RuntimeError("staging signature verifier unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if Path(candidate).resolve(strict=True) != module.PACKAGE.resolve(strict=True):
        raise ValueError("candidate is not the signed staging release")
    proof = module.verify()
    if (proof.get("status") != "STAGING_ED25519_MANIFEST_SIGNATURE_VERIFIED"
            or proof.get("production_release_approved") is not False
            or proof.get("package_sha256") != sha256(candidate)):
        raise ValueError("signed staging release proof mismatch")
    return proof


def stage_runtime_probe():
    """Read-only local staging API probe, never production or remote URLs."""
    endpoint = "http://127.0.0.1:18690"
    with urlopen(endpoint + "/health", timeout=3) as response:
        if response.status != 200:
            raise RuntimeError("staging health unavailable")
        health = json.load(response)
    if health.get("service") != "openserverdesk" or health.get("environment") != "staging":
        raise RuntimeError("unexpected staging runtime identity")
    with urlopen(endpoint + "/api/v1/migration/readiness", timeout=3) as response:
        if response.status != 200:
            raise RuntimeError("staging readiness unavailable")
        readiness = json.load(response)
    if readiness.get("migration_allowed") is not False:
        raise RuntimeError("staging runtime unexpectedly permits production migration")
    return {"endpoint": endpoint, "service": "openserverdesk",
            "environment": "staging", "migration_allowed": False}


def orchestrate_fixture(target, bundle, app_root, candidate=None, probe_runtime=False):
    """Activate disposable fixture only after a verified app snapshot.

    On post-activation verification failure, restore the service pair from its
    durable journal. Never touches the live application data or production.
    """
    from m1_fixture_activation import status as fixture_status
    before = checkpoint_integrity(target, app_root)
    if (before["service"]["state"] != "IDLE" or
            before["applications"] not in ("SNAPSHOT_AVAILABLE", "RESTORED") or
            before["application_integrity"] != "VERIFIED"):
        raise RuntimeError("verified app snapshot and idle service fixture required")
    runtime = stage_runtime_probe() if probe_runtime else None
    package = candidate_identity(candidate) if candidate is not None else None
    signature = verified_stage_release(candidate) if candidate is not None else None
    # Require an actual staging owner and no active stage-owned Docker
    # writer immediately before activation. This does not stop containers.
    root = root_fixture(app_root)
    stage_owner = app_quiesced(root)
    if stage_owner != app_owner(root):
        raise RuntimeError("stage ownership changed during quiescence check")
    try:
        fixture_execute("activate", target, bundle)
        after = checkpoint_integrity(target, app_root)
        if (after["service"]["state"] != "ROLLBACK_AVAILABLE" or
                after["service"].get("journal_integrity") != "VERIFIED" or
                after["application_integrity"] != "VERIFIED"):
            raise RuntimeError("post-activation checkpoint integrity failed")
        return {"scope": "STAGING_FIXTURE_ORCHESTRATION_ONLY",
                "result": "ACTIVATED_WITH_UNDO", "checkpoint": after,
                "stage_owner": stage_owner, "stage_writer_quiesced": True,
                "candidate": package, "staging_signature": signature,
                "runtime": runtime,
                "migration_allowed": False, "production_modified": False}
    except Exception:
        # If activation raised after journaling but before returning, the
        # durable journal may still exist; recover only when verified.
        # Recovery must not depend on the application checkpoint remaining
        # readable: that is often the very reason activation failed.
        # Use only the isolated service journal's own integrity proof.
        from m1_fixture_activation import status as fixture_status
        from journaled_pair import digest as pair_digest
        state = fixture_status(target)
        if state["state"] == "ROLLBACK_AVAILABLE":
            journal = Path(target).resolve() / ".osd-undo"
            try:
                manifest_file = journal / "manifest.json"
                if manifest_file.is_symlink():
                    raise ValueError("symlinked undo manifest")
                manifest = json.loads(manifest_file.read_text())
                if set(manifest) != {"userservice", "user.db"}:
                    raise ValueError("unexpected undo manifest")
                for name, expected in manifest.items():
                    source = journal / name
                    if source.is_symlink() or pair_digest(source) != expected:
                        raise ValueError("corrupted undo journal")
            except (OSError, ValueError, TypeError, KeyError) as err:
                raise RuntimeError("automatic rollback blocked: unsafe undo journal") from err
            fixture_execute("rollback", target)
        raise

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--fixture-action", choices=("status", "activate", "rollback"),
                   help="disposable temporary fixture only; never performs production cutover")
    p.add_argument("--fixture-target", type=Path)
    p.add_argument("--fixture-bundle", type=Path)
    p.add_argument("--app-fixture-action", choices=("snapshot", "restore"),
                   help="multi-project isolated staging snapshot/restore only")
    p.add_argument("--app-fixture", type=Path)
    p.add_argument("--probe-stage-runtime", action="store_true",
                   help="verify local staging health and migration lock before activation")
    p.add_argument("--stage-candidate", type=Path,
                   help="optional read-only .deb identity for staging orchestration")
    p.add_argument("--orchestrate-fixture", action="store_true",
                   help="verified app checkpoint, fixture activation, rollback on failure")
    p.add_argument("--checkpoint", action="store_true",
                   help="read-only combined fixture checkpoint; no production actions")
    p.add_argument("--backup",type=Path)
    p.add_argument("--candidate",type=Path)
    p.add_argument("--report",type=Path)
    args=p.parse_args()
    if args.orchestrate_fixture:
        if (args.checkpoint or args.fixture_action or args.app_fixture_action
                or not args.fixture_target or not args.fixture_bundle or not args.app_fixture
                or args.backup or args.candidate):
            p.error("orchestration requires fixture target, bundle and app fixture only")
        result = orchestrate_fixture(args.fixture_target, args.fixture_bundle,
                                     args.app_fixture, args.stage_candidate,
                                     args.probe_stage_runtime)
    elif args.checkpoint:
        if (args.probe_stage_runtime or args.stage_candidate or args.app_fixture_action or args.fixture_action or not args.app_fixture
                or not args.fixture_target or args.fixture_bundle or args.backup
                or args.candidate):
            p.error("checkpoint requires --fixture-target and --app-fixture only")
        result = checkpoint_integrity(args.fixture_target, args.app_fixture)
    elif args.app_fixture_action:
        if (args.probe_stage_runtime or args.stage_candidate or args.orchestrate_fixture or not args.app_fixture or args.fixture_action or args.fixture_target
                or args.fixture_bundle or args.backup or args.candidate):
            p.error("app fixture mode requires --app-fixture only")
        result = (app_snapshot(args.app_fixture) if args.app_fixture_action == "snapshot"
                  else app_restore(args.app_fixture))
    elif args.fixture_action:
        if args.probe_stage_runtime or args.stage_candidate or args.orchestrate_fixture or args.backup or args.candidate or args.app_fixture or not args.fixture_target:
            p.error("fixture mode requires --fixture-target and forbids --backup/--candidate")
        result = fixture_execute(args.fixture_action, args.fixture_target, args.fixture_bundle)
    else:
        if args.probe_stage_runtime or args.stage_candidate or args.fixture_target or args.fixture_bundle or args.app_fixture or args.app_fixture_action:
            p.error("fixture arguments require --fixture-action")
        if not args.backup:
            p.error("--backup required for production read-only preflight")
        result=gate(args.backup,args.candidate)
    text=json.dumps(result,indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(text+"\n")
    print(text)
if __name__=="__main__":main()
