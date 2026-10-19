#!/usr/bin/env python3
"""Read-only integration between stage App Management and Compose fixture planner.

Never starts/stops applications, reads credentials, or touches production.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tools"))

from stage_apps import enabled, list_apps, AppError
from stage_compose import list_projects
from synthetic_compose_rehearsal import translate_stage_resources
from compose_semantics import isolated_deployment_plan


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


if __name__ == "__main__":
    # Synthetic input only. Source app configs are never logged.
    fixture = {"services": {"database": {"image": "discarded"},
        "frontend": {"image": "discarded", "depends_on": ["database"],
                     "volumes": ["/discarded:/discarded"]}}}
    print(json.dumps(report(fixture), sort_keys=True))
