#!/usr/bin/env python3
"""Stage-owned App Management and Compose lifecycle integration.

Mutations delegate to the existing guarded stage Compose manager only.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tools"))

from stage_apps import enabled, list_apps, AppError
from stage_compose import list_projects, action as compose_action, TEMPLATES
from synthetic_compose_rehearsal import translate_stage_resources
from compose_semantics import isolated_deployment_plan


def managed_action(operation, *, template=None, project=None):
    """Use the existing owner-guarded staging Compose manager; no raw Docker."""
    if operation == "install":
        if template not in TEMPLATES or project is not None:
            raise AppError("unsupported_staging_template", 400)
        return compose_action("install", template=template)
    if operation not in ("start", "stop", "restart", "uninstall"):
        raise AppError("unsupported_compose_action", 400)
    if template is not None or not isinstance(project, str):
        raise AppError("invalid_compose_project_name", 400)
    return compose_action(operation, project=project)


def report(doc):
    translated, counts = translate_stage_resources(doc)
    plan = isolated_deployment_plan(translated)
    result = {
        "scope": "READ_ONLY_STAGE_APP_MANAGEMENT_COMPOSE_BRIDGE",
        "stage_manager_enabled": enabled(),
        "compose_service_count": plan["service_count"],
        "dependency_order": plan["service_order"],
        "source_resource_declarations": counts,
        "real_app_imports_verified": 0,
        "production_mutation_allowed": False,
    }
    if result["stage_manager_enabled"]:
        try:
            apps = list_apps()
            result["registered_stage_apps"] = len(apps["apps"])
            result["running_stage_apps"] = sum(bool(a["running"]) for a in apps["apps"])
            compose = list_projects()
            result["registered_stage_compose_projects"] = len(compose["projects"])
            result["running_stage_compose_projects"] = sum(
                bool(p["running"]) for p in compose["projects"])
            result["stage_compose_management_integrated"] = True
        except AppError:
            result["stage_inventory_available"] = False
    return result


def lifecycle_smoke():
    """One bounded staging-only install/lifecycle/uninstall integration."""
    before = list_projects()["projects"]
    if before:
        raise AppError("stage_compose_inventory_not_empty_for_smoke", 409)
    installed = managed_action("install", template="task-worker")
    project = installed["app"]["project"]
    operations = ["stop", "start", "restart"]
    try:
        for op in operations:
            result = managed_action(op, project=project)
            if result["operation"] != op:
                raise RuntimeError("stage Compose lifecycle operation mismatch")
        if len(list_projects()["projects"]) != 1:
            raise RuntimeError("stage Compose inventory missing managed fixture")
    finally:
        managed_action("uninstall", project=project)
    if list_projects()["projects"]:
        raise RuntimeError("stage Compose fixture remained registered")
    return {"scope": "STAGE_COMPOSE_OWNED_FIXTURE_ONLY",
            "install_stop_start_restart_uninstall": "PASS",
            "stage_inventory_restored": True,
            "production_mutation_allowed": False}


if __name__ == "__main__":
    if "--lifecycle-smoke" in sys.argv:
        print(json.dumps(lifecycle_smoke(), sort_keys=True))
        sys.exit(0)
    # Synthetic input only. Source app configs are never logged.
    fixture = {"services": {"database": {"image": "discarded"},
        "frontend": {"image": "discarded", "depends_on": ["database"],
                     "volumes": ["/discarded:/discarded"]}}}
    print(json.dumps(report(fixture), sort_keys=True))
