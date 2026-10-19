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
    for name, result, key in sources:
        if result.get("production_mutation_allowed") is not False:
            raise ValueError("unsafe_stage_inventory_scope")
        counts[name] = len(result[key])
    return {"scope": "stage_owned_inventory_only",
            "counts": counts,
            "total": sum(counts.values()),
            "production_mutation_allowed": False}
