"""Authenticated staging-only inventory aggregation; never mutates Docker."""
from stage_container_health import readiness as health_readiness
from stage_apps import AppError
from stage_apps import list_apps
from stage_compose import list_projects
from stage_store_installer import list_installs
from stage_store_general import listing as list_store_general
from stage_store_runtime import listing as list_store_compiled


def inventory():
    # Compiled projects can include historical root-owned staging data.
    # Never change protected file permissions or silently count them as zero.
    # Keep the four independent stage inventory sources available even when
    # compiled recovery/provenance metadata is temporarily unreadable.
    try:
        compiled = list_store_compiled()
    except (AppError, OSError, ValueError):
        compiled = None
    sources = (
        ("docker", list_apps(), "apps"),
        ("compose", list_projects(), "projects"),
        ("store_pilot", list_installs(), "apps"),
        ("store_general", list_store_general(), "apps"),
        ("store_compiled", compiled, "apps"),
    )
    counts = {}
    applications = []
    unavailable_sources = []
    for name, result, key in sources:
        if result is None:
            counts[name] = None
            unavailable_sources.append(name)
            continue
        if result.get("production_mutation_allowed") is not False:
            raise ValueError("unsafe_stage_inventory_scope")
        entries = result[key]
        counts[name] = len(entries)
        for entry in entries:
            if entry.get("production_mutation_allowed", False) is not False:
                raise ValueError("unsafe_stage_application_scope")
            app_name = entry.get("app_id") or entry.get("name") or entry.get("project")
            if not isinstance(app_name, str) or not app_name:
                raise ValueError("invalid_stage_application_identity")
            if name == "store_compiled":
                assessment = entry.get("health_summary")
                if not isinstance(assessment, dict):
                    raise ValueError("invalid_compiled_stage_health_summary")
                running = entry.get("all_running")
                if not isinstance(running, bool) or running != (
                    assessment.get("lifecycle") == "running"):
                    raise ValueError("invalid_compiled_stage_running_state")
                health_status = assessment["health_status"]
                readiness = assessment["readiness"]
                lifecycle = assessment["lifecycle"]
                service_counts = assessment["counts"]
                partial_failure = assessment["partial_failure"]
            else:
                running = entry.get("running")
                if not isinstance(running, bool):
                    raise ValueError("invalid_stage_running_state")
                health_status = entry.get("health_status", "not_configured")
                readiness = health_readiness(running, health_status)
                lifecycle = "running" if running else "stopped"
                service_counts = None
                partial_failure = False
            applications.append({
                "source": name,
                "name": app_name,
                "project": entry.get("project") if isinstance(entry.get("project"), str) else None,
                "running": running,
                "lifecycle": lifecycle,
                "readiness": readiness,
                "health_status": health_status,
                "service_counts": service_counts,
                "partial_failure": partial_failure,
            })
    return {"scope": "stage_owned_inventory_only",
            "counts": counts,
            "total": sum(value for value in counts.values() if value is not None),
            "complete": not unavailable_sources,
            "unavailable_sources": unavailable_sources,
            "applications": applications,
            "lifecycle_counts": {
                "running": sum(1 for app in applications if app["running"]),
                "partially_running": sum(1 for app in applications
                                         if app["lifecycle"] == "partially_running"),
                "stopped": sum(1 for app in applications
                               if app["lifecycle"] == "stopped"),
            },
            "production_mutation_allowed": False}
