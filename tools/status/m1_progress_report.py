#!/usr/bin/env python3
"""Audited, one-shot weighted M1 release acceptance status.

The score is completed scope weight, NOT elapsed time or a completion ETA.
Each weight only counts on explicitly verified evidence, with NO speculative
partial credit. Never runs mutating Docker or host commands.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
OUT = Path("/opt/openserverdesk-dev/runtime-stage/progress")
PKG = Path("/opt/openserverdesk-dev/build/openserverdesk-m1-candidate_0.6.19_amd64.deb")
URL = "http://127.0.0.1:18690"

# Explicitly frozen acceptance criteria/weights. Add new independently
# verified evidence before promoting any outstanding criterion.
GATES = (
    ("payload", "Complete 6-component staging payload (unsigned)", 8),
    ("six_boot", "Six-service isolated boot + routed UserService", 4),
    ("docker_ui", "Live read-only Docker/Compose dashboard", 8),
    ("data_inventory", "Real Docker bind/data coverage inventory", 4),
    ("fixture_recovery", "Two-project staged SQLite/Compose/bind restore", 8),
    ("config_recovery", "Real SSD backup and independent restore of platform configuration only", 8),
    ("full_runtime", "Full authenticated AppManagement/LocalStorage workflows", 18),
    ("config_atomicity", "Proven consistent cross-service configuration migration", 12),
    ("cutover_rollback", "Production-equivalent safe activation + full rollback", 20),
    ("security_release", "Signed release + independent security acceptance", 10),
)
assert sum(weight for _, _, weight in GATES) == 100


def command(*args, timeout=7):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.stdout.strip() if p.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def api(route):
    try:
        with urlopen(URL + route, timeout=3) as response:
            if response.status != 200:
                return None
            if route == "/ui":
                return response.read(80000).decode("utf-8", "replace")
            return json.load(response)
    except (OSError, ValueError, TimeoutError):
        return None


def file_has(path, phrase):
    try:
        return path.is_file() and phrase in path.read_text()
    except (OSError, UnicodeError):
        return False


def collect():
    sha = command("git", "-C", str(ROOT), "rev-parse", "--short=12", "HEAD")
    when = command("git", "-C", str(ROOT), "show", "-s", "--format=%cI", "HEAD")
    message = command("git", "-C", str(ROOT), "show", "-s", "--format=%s", "HEAD")
    status = command("git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no")
    ver = command("dpkg-deb", "--field", str(PKG), "Version")
    pkg_files = command("dpkg-deb", "--contents", str(PKG), timeout=16) if ver == "0.6.19" else ""
    required = (
        "usr/lib/openserverdesk/bin/casaos",
        "usr/lib/openserverdesk/bin/CasaOS-Gateway",
        "usr/lib/openserverdesk/bin/CasaOS-MessageBus",
        "usr/lib/openserverdesk/bin/CasaOS-UserService",
        "usr/lib/openserverdesk/bin/CasaOS-AppManagement",
        "usr/lib/openserverdesk/bin/CasaOS-LocalStorage",
        "usr/share/openserverdesk/www/index.html",
    )
    payload = bool(pkg_files) and all("./" + f in pkg_files for f in required)
    ui = api("/ui")
    containers = api("/api/v1/docker/containers")
    coverage = api("/api/v1/migration/data-coverage")
    readiness = api("/api/v1/migration/readiness")
    healthy = api("/health")
    checks = {
        "payload": payload,
        # Historical evidence is explicitly labelled, NOT a fresh run.
        "six_boot": payload and file_has(
            ROOT / "docs/M1_FULL6_STAGING_BOOT_20261015.md",
            "FULL6_ISOLATED_PROCESS_BOOT_AND_USER_ROUTE_PASS"),
        "docker_ui": isinstance(ui, str) and "OpenServerDesk" in ui
        and isinstance(containers, dict)
        and containers.get("source") == "local_docker_engine_read_only"
        and type(containers.get("container_count")) is int
        and containers["container_count"] >= 1,
        "data_inventory": isinstance(coverage, dict)
        and type(coverage.get("unique_bind_source_count")) is int
        and coverage["unique_bind_source_count"] > 0
        and coverage.get("migration_allowed") is False,
        "fixture_recovery": payload and all((ROOT / p).is_file() for p in (
            "tools/migration/full_app_recovery.py",
            "tools/staging/verify-real-multiproject-recovery.py",
            "docs/M1_MULTI_APP_RECOVERY_20261015.md",
        )) and file_has(
            ROOT / "docs/M1_MULTI_APP_RECOVERY_20261015.md",
            "TWO_REAL_DOCKER_APP_PROJECTS_QUIESCE_BACKUP_RESTORE_AND_BOOT_PASS"),
        # Full release acceptance is distinct from real but NON-atomic
        # scoped configuration recovery performed on the NAS SSD.
        "config_recovery": False,
        "full_runtime": False,
        "config_atomicity": False,
        "cutover_rollback": False,
        "security_release": False,
    }
    # Root-only verifier wrote a redacted acceptance report after checking
    # the actual backup and recovery on an SSD separate from source disk.
    # The user-disabled cron must NOT be re-enabled to update these metrics.
    proof_file = Path(
        "/opt/openserverdesk-dev/runtime-stage/"
        "M1_RELEASE_DECISION_CONFIG_SSD_20261016.json")
    try:
        attestation = json.loads(proof_file.read_text())
        recovery = attestation["configuration_recovery_acceptance"]
        checks["config_recovery"] = (
            payload and ver == "0.6.19"
            and attestation["migration_allowed"] is False
            and recovery["platform_backup_verified"] is True
            and recovery["staging_restore_verified"] is True
            and recovery["external_nextcloud_user_uploads_copied"] is False
            and recovery["platform_cluster_snapshot_atomic"] is False
            and recovery["verified_config_files"] >= 1
            and recovery["verified_sqlite_dbs"] >= 3)
    except (OSError, ValueError, TypeError, KeyError):
        checks["config_recovery"] = False
    milestones = [
        {"id": id_, "label": label, "weight_percent": weight, "verified": bool(checks[id_]),
         "evidence_class": (
             "live_readonly" if id_ in ("docker_ui", "data_inventory")
             else "artifact_and_recorded_test" if id_ in ("payload", "six_boot", "fixture_recovery", "config_recovery")
             else "unverified"
         )}
        for id_, label, weight in GATES
    ]
    progress = sum(x["weight_percent"] for x in milestones if x["verified"])
    prod = {
        name: command("systemctl", "is-active", name)
        for name in (
            "casaos", "casaos-gateway", "casaos-user-service",
            "casaos-app-management", "casaos-local-storage",
            "casaos-message-bus",
        )
    }
    now = dt.datetime.now(dt.timezone.utc)
    return {
        "schema_version": 1,
        "checked_at_utc": now.isoformat(timespec="seconds"),
        "checked_at_wib": now.astimezone(
            dt.timezone(dt.timedelta(hours=7))
        ).isoformat(timespec="seconds"),
        "metric": "weighted_scope_accepted_not_time_estimate",
        "progress_percent": progress,
        "milestones": milestones,
        "git_sha": sha, "git_commit_at": when, "git_message": message,
        "tracked_working_tree_dirty": bool(status),
        "package_version": ver or None,
        "staging_http": {
            "health": 200 if isinstance(healthy, dict) else 503,
            "ui": 200 if isinstance(ui, str) else 503,
            "docker": 200 if isinstance(containers, dict) else 503,
            "coverage": 200 if isinstance(coverage, dict) else 503,
            "readiness": 200 if isinstance(readiness, dict) else 503,
        },
        "docker_count": containers.get("container_count") if isinstance(containers, dict) else None,
        "compose_count": len(containers.get("compose_projects", [])) if isinstance(containers, dict) else None,
        "production_service_status": prod,
        "migration_allowed": bool(isinstance(readiness, dict) and readiness.get("migration_allowed") is True),
        "migration_reason": readiness.get("reason", "unavailable") if isinstance(readiness, dict) else "unavailable",
        "next_priority": "Complete real full-stack AppManagement/LocalStorage authenticated integration and production-equivalent recovery/rollback.",
    }


def publish():
    if not OUT.is_dir() or OUT.is_symlink():
        raise RuntimeError("dedicated staging report directory missing")
    report = collect()
    current = OUT / "latest.json"
    previous = None
    if current.is_file() and not current.is_symlink():
        try:
            previous = json.loads(current.read_text())
        except (ValueError, OSError):
            previous = None
    report["delta_percent_since_previous"] = (
        report["progress_percent"] - previous["progress_percent"]
        if isinstance(previous, dict) and type(previous.get("progress_percent")) is int
        else None
    )
    report["new_git_commit_since_previous"] = (
        report["git_sha"] != previous.get("git_sha")
        if isinstance(previous, dict) else None
    )
    report["milestone_change_note"] = (
        "No newly verified release milestone in this interval."
        if report["delta_percent_since_previous"] == 0
        else "Verified milestone score changed; inspect the evidence and commit."
        if report["delta_percent_since_previous"] is not None
        else "First baseline snapshot."
    )
    fd, tmpname = tempfile.mkstemp(prefix=".m1-status-", dir=OUT)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(report, f, ensure_ascii=False, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmpname, 0o644)
        os.replace(tmpname, current)
    finally:
        Path(tmpname).unlink(missing_ok=True)
    with (OUT / "history.jsonl").open("a") as f:
        f.write(json.dumps({
            k: report[k] for k in (
                "checked_at_wib", "progress_percent", "delta_percent_since_previous",
                "git_sha", "migration_allowed", "staging_http",
            )
        }, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    print(json.dumps({
        "checked_at_wib": report["checked_at_wib"],
        "progress_percent": report["progress_percent"],
        "delta_percent_since_previous": report["delta_percent_since_previous"],
        "git_sha": report["git_sha"],
        "migration_allowed": report["migration_allowed"],
    }, sort_keys=True))


if __name__ == "__main__":
    publish()
