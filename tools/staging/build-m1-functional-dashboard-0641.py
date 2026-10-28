#!/usr/bin/env python3
"""Package the running read-only local Docker dashboard into full M1 staging payload.

No systemd host installation, activation, maintainer hooks or production changes.
"""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[2]
BASE = Path("/home/andre/projects/openserverdesk/operations/build/openserverdesk-m1-candidate_0.5.0_amd64.deb")
OUT = Path("/home/andre/projects/openserverdesk/operations/build/openserverdesk-m1-candidate_0.6.41_amd64.deb")
STAGE = Path("/home/andre/projects/openserverdesk/operations/runtime-stage")

def main():
    if not BASE.is_file():
        raise FileNotFoundError(BASE)
    with tempfile.TemporaryDirectory(prefix="m1-real-docker-ui-", dir=STAGE) as work:
        tree = Path(work) / "root"
        tree.mkdir()
        subprocess.run(["dpkg-deb", "--extract", str(BASE), str(tree)], check=True)
        server = tree/"usr/lib/openserverdesk/server"
        for name in ("app.py", "docker_readonly.py", "readiness.py", "stage_apps.py", "stage_storage.py", "stage_recovery.py", "stage_compose.py",
                     "stage_compose_recovery.py", "host_status.py", "stage_users.py",
                     "docker_metrics.py", "stage_topology.py", "stage_topology_health.py", "casaos_appstore.py", "stage_store_installer.py", "stage_store_general.py", "stage_store_coverage.py", "stage_store_compiler.py", "stage_store_runtime.py", "stage_store_data.py", "stage_app_gateway.py"):
            shutil.copy2(REPO/"server"/name, server/name)
        (server/"release-version.txt").write_text("0.6.41\n")
        # Ship the read-only real Docker/Compose data coverage inventory,
        # never invoke it during package installation.
        migration_tools = tree/"usr/lib/openserverdesk/tools"
        migration_tools.mkdir(parents=True, exist_ok=True)
        for module in ("m1_app_data_inventory.py", "m1_topology_preflight.py",
                       "full_app_recovery.py", "volume_fixture.py",
                       "m1_cold_backup.py", "m1_storage_safety_gate.py",
                       "m1_platform_scope.py", "m1_config_recovery.py",
                       "m1_service_unit_backup.py", "m1_cutover_readiness.py"):
            shutil.copy2(REPO/"tools/migration"/module,
                         migration_tools/module)
        ui = server/"ui"
        ui.mkdir(exist_ok=True)
        for name in ("index.html", "style.css", "app.js"):
            shutil.copy2(REPO/"server/ui"/name, ui/name)
        # No production service activation. Runtime socket read disabled unless
        # explicitly opted into a trusted local staging invocation.
        control = tree/"DEBIAN"
        control.mkdir()
        (control/"control").write_text(
            "Package: openserverdesk-m1-candidate\nVersion: 0.6.41\n"
            "Section: admin\nPriority: optional\nArchitecture: amd64\n"
            "Maintainer: OpenServerDesk staging <staging@example.invalid>\n"
            "Description: Full component staging payload with read-only Docker inventory UI\n"
        )
        docs = tree/"usr/share/doc/openserverdesk-m1-candidate"
        (docs/"DOCKER_UI").write_text(
            "Opt-in staging only: OSD_DOCKER_READ_ONLY=1 enables Docker GET inventory.\n"
            "Never expose this inventory to unauthenticated networks.\n"
            "No production cutover, write actions, or migration allowed.\n"
        )
        partial = OUT.with_suffix(".partial.deb")
        try:
            subprocess.run(["dpkg-deb", "--build", "--root-owner-group",
                            "-Zgzip", "-z1", str(tree), str(partial)],
                           check=True, stdout=subprocess.DEVNULL, timeout=150)
            os.replace(partial, OUT)
        finally:
            partial.unlink(missing_ok=True)
    with OUT.open("rb") as f:
        print("M1_STAGING_FUNCTIONAL_UI_PACKAGE_BUILT_PASS")
        print("PACKAGE", OUT)
        print("SHA256", hashlib.file_digest(f, "sha256").hexdigest())

if __name__=="__main__":
    main()
