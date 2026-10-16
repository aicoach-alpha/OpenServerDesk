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
PKG = Path("/opt/openserverdesk-dev/build/openserverdesk-m1-candidate_0.6.11_amd64.deb")
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
            or pkg_version.stdout.strip() != "0.6.11"):
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
    blockers["platform_configuration_recovery"] = (
        "CasaOS configuration, internal SQLite and selected Compose definitions "
        "must be verified in an isolated recovery, without moving or reading "
        "external HDD/Nextcloud user uploads."
    )
    try:
        from m1_storage_safety_gate import inspect as inspect_storage
        storage = inspect_storage()
        if not storage["independent_target"]["supplied"]:
            blockers["platform_config_backup_destination"] = (
                "Scoped CasaOS/Compose config recovery destination is not yet "
                "configured and verified. A 2 TB copy of Nextcloud user uploads "
                "is NOT part of M1 migration."
            )
    except Exception:
        storage = {"status": "platform_config_scope_unavailable",
                   "migration_allowed": False}
        blockers["platform_config_backup_destination"] = (
            "Scoped platform config backup preflight unavailable; fail closed. "
            "External HDD user data must not be accessed."
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
