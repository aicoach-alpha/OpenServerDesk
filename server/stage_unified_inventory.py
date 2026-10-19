"""Authenticated staging-only inventory aggregation; never mutates Docker."""
from stage_apps import list_apps
from stage_compose import list_projects
from stage_store_installer import list_installs
from stage_store_general import listing as list_store_general


def inventory():
    sources = (
        ("docker", list_apps(), "apps"),
        ("compose", list_projects(), "projects"),
        ("store_pilot", list_installs(), "apps"),
        ("store_general", list_store_general(), "apps"),
    )
    counts = {}
    applications = []
    for name, result, key in sources:
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
            applications.append({
                "source": name,
                "name": app_name,
                "project": entry.get("project") if isinstance(entry.get("project"), str) else None,
                "running": bool(entry.get("running", False)),
            })
    return {"scope": "stage_owned_inventory_only",
            "counts": counts,
            "total": sum(counts.values()),
            "applications": applications,
            "production_mutation_allowed": False}
