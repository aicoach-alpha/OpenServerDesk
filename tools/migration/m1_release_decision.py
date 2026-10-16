#!/usr/bin/env python3
"""One consolidated, read-only M1 final acceptance decision.

Does not upgrade, migrate, stop, delete or alter CasaOS, Docker workloads,
existing package services, data volumes or system service units.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = Path("/opt/openserverdesk-dev/build/openserverdesk-m1-candidate_0.6.16_amd64.deb")
CORE = ["casaos", "casaos-gateway", "casaos-user-service", "casaos-app-management",
        "casaos-local-storage", "casaos-message-bus"]


def command(*args):
    return subprocess.run(args, capture_output=True, text=True, timeout=20)


def decide():
    if not PKG.is_file():
        raise RuntimeError("candidate package missing")
    contents = command("dpkg-deb", "--contents", str(PKG))
    if contents.returncode:
        raise RuntimeError("package contents cannot be inspected")
    pkg_name = command("dpkg-deb", "--field", str(PKG), "Package")
    pkg_version = command("dpkg-deb", "--field", str(PKG), "Version")
    if (pkg_name.returncode or pkg_version.returncode
            or pkg_name.stdout.strip() != "openserverdesk-m1-candidate"
            or pkg_version.stdout.strip() != "0.6.16"):
        raise RuntimeError("candidate metadata does not match exact release version")
    files = contents.stdout
    package_components = {
        "core": "./usr/lib/openserverdesk/bin/casaos" in files,
        "appfile2compose": "./usr/lib/openserverdesk/bin/appfile2compose" in files,
        "gateway": "./usr/lib/openserverdesk/bin/CasaOS-Gateway" in files,
        "message_bus": "./usr/lib/openserverdesk/bin/CasaOS-MessageBus" in files,
        "user_service": "./usr/lib/openserverdesk/bin/CasaOS-UserService" in files,
        "api": "./usr/lib/openserverdesk/server/app.py" in files,
        "api_unit": "./usr/lib/systemd/system/openserverdesk-m1-candidate.service" in files,
        "app_management": "CasaOS-AppManagement" in files,
        "local_storage": "CasaOS-LocalStorage" in files,
        "full_product_dashboard": "./usr/share/openserverdesk/www/index.html" in files,
    }
    installer = (ROOT/"tools/migration/migrate_installer.py").read_text()
    status = {unit: command("systemctl", "is-active", unit).stdout.strip() for unit in CORE}
    docker_ps = command("docker", "ps", "--format", "{{.ID}}")
    if docker_ps.returncode:
        raise RuntimeError("Docker read-only inventory failed")
    live_count = len([line for line in docker_ps.stdout.splitlines() if line])
    # This is a data-preservation blocker, not an assumption that all Docker
    # stacks could be safely replaced with the existing three binaries.
    blockers = {}
    if not all(package_components.values()):
        blockers["full_product_payload"] = (
            "Candidate package is missing one or more essential product components."
        )
    else:
        blockers["full_product_runtime_integration"] = (
            "All six packaged service processes have booted in an isolated "
            "staging namespace with dashboard and UserService route; full "
            "AppManagement/Docker operations, LocalStorage mounts, application "
            "persistence, UI functionality and production-equivalent integration "
            "remain unverified."
        )
    if '"activation_implemented":False' in installer or '"rollback_implemented":False' in installer:
        blockers["complete_activation_rollback_controller"] = (
            "Migration installer explicitly reports activation/rollback not implemented."
        )
    # Replacing CasaOS is NOT a migration of Docker user bind data or
    # Nextcloud uploads. Only platform configuration and Compose definitions
    # require backup/restore; all user-data mount references stay unchanged.
    config_acceptance = {
        "platform_backup_verified": False,
        "staging_restore_verified": False,
        "external_nextcloud_user_uploads_copied": False,
        "platform_cluster_snapshot_atomic": False,
    }
    try:
        from m1_config_recovery import BACKUP_ROOT, sha, verify, verify_tree
        from m1_storage_safety_gate import inspect as inspect_storage
        from m1_platform_scope import select as select_platform
        storage = inspect_storage(Path("/mnt/ssd-turbo"))
        backup_record = json.loads(Path(
            "/opt/openserverdesk-dev/runtime-stage/"
            "M1_CONFIG_ONLY_SSD_BACKUP_LIVE_20261016.json").read_text())
        restore_record = json.loads(Path(
            "/opt/openserverdesk-dev/runtime-stage/"
            "M1_CONFIG_ONLY_SSD_RESTORE_LIVE_20261016.json").read_text())
        backup_id = backup_record["backup_id"]
        manifest, actual = verify(backup_id)
        recovery_tree = BACKUP_ROOT / "restored" / backup_id
        restored = verify_tree(recovery_tree, manifest)
        current_source_scope, _current_sources = select_platform()
        proof_ok = (
            backup_record.get("manifest_sha256") == sha(
                BACKUP_ROOT / backup_id / "manifest.json")
            and backup_record.get("backup_device_is_ssd") is True
            and backup_record.get("user_data_copied") is False
            and backup_record.get("production_modified") is False
            and backup_record.get("sqlite_verified", 0) >= 3
            and backup_record.get("files_verified", 0) > 0
            and actual == restored
            and restore_record.get("backup_id") == backup_id
            and restore_record.get("user_data_copied") is False
            and restore_record.get("production_modified") is False
            and restore_record.get("original_platform_config_overwritten") is False
            and current_source_scope.get("external_user_data_copied") is False
            and current_source_scope.get("external_user_data_inspected") is False
            and storage["independent_target"]["different_device_from_every_source"]
        )
        config_acceptance.update({
            "platform_backup_verified": bool(proof_ok),
            "staging_restore_verified": bool(proof_ok),
            "selected_platform_sources": (
                current_source_scope["selected_config_source_count"]),
            "verified_config_files": actual["files_verified"] if proof_ok else 0,
            "verified_sqlite_dbs": actual["sqlite_verified"] if proof_ok else 0,
        })
        if not proof_ok:
            blockers["platform_configuration_recovery"] = (
                "Platform-only SSD backup and staged restore evidence mismatch."
            )
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, PermissionError):
        storage = {"status": "platform_config_scope_unavailable",
                   "migration_allowed": False}
        blockers["platform_configuration_recovery"] = (
            "Cannot independently verify selected CasaOS configuration backup "
            "and isolated restore; production cutover remains denied."
        )
    if not config_acceptance["platform_backup_verified"]:
        blockers["platform_config_backup_destination"] = (
            "No verified independent destination for scoped platform configuration. "
            "Nextcloud uploads and external HDD are EXCLUDED from migration."
        )
    else:
        blockers["platform_configuration_atomic_consistency"] = (
            "Three SQLite databases were restored and integrity-checked "
            "individually, but cross-service application state and transaction "
            "consistency during live backup are not yet proven. No actual "
            "production switchover is authorized."
        )
    blockers["signed_release_and_security_acceptance"] = (
        "No validated signed production release or completed independent M1 "
        "security/pentest acceptance is supplied."
    )
    return {
        "milestone": "M1.5 full replacement", "decision": "BLOCKED" if blockers else "PASS",
        "migration_allowed": False, "safe_to_cutover": False,
        "candidate_package": PKG.name, "candidate_sha256": hashlib.sha256(PKG.read_bytes()).hexdigest(),
        "package_components": package_components, "existing_casaos_services": status,
        "running_docker_container_count": live_count,
        "storage_safety":storage,
        "configuration_recovery_acceptance": config_acceptance,
        "unmet_exit_criteria": blockers,
        "evidence": {
            "source": "GitHub aicoach-alpha/OpenServerDesk",
            "criteria": "docs/ROADMAP.md M1.5; README.md",
            "staging_passes_preserved": True,
            "production_changed": False,
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()
    result = decide()
    encoded = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded)
    print(encoded)
    raise SystemExit(0 if result["decision"] == "PASS" else 2)


if __name__ == "__main__":
    main()
