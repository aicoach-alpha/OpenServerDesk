"""Read-only health and ownership checks for isolated Compose topologies.

Reports only staging-owned project identifiers and counts; no Docker logs,
environment, Nextcloud files, or application storage content is returned.
Individual failures remain visible instead of hiding all healthy projects.
"""
from __future__ import annotations
import datetime as dt
from stage_apps import guarded, AppError
from stage_topology import _registry, _verified, MAX_PROJECTS

KNOWN_ERRORS = {
    "topology_project_files_invalid",
    "topology_configuration_changed",
    "invalid_topology_project",
    "unsafe_topology_root",
    "topology_container_inspection_failed",
    "topology_container_provenance_violation",
    "unexpected_topology_container_count",
    "stage_compose_command_failed",
    "isolated_compose_command_failed",
}


def inspect():
    with guarded():
        registry = _registry()
        results = []
        for project, entry in sorted(registry.items()):
            try:
                item = _verified(project, entry)
                states = item["services"]
                healthy = all(service["running"] for service in states)
                results.append({
                    "project":project,
                    "status":"healthy" if healthy else "degraded",
                    "expected_services":len(entry["containers"]),
                    "running_services":sum(bool(x["running"]) for x in states),
                    "ownership_verified":True,
                    "issue":None,
                })
            except AppError as err:
                # Never reveal Docker stderr, source paths or raw labels.
                results.append({
                    "project":project,
                    "status":"unavailable",
                    "expected_services":len(entry["containers"]),
                    "running_services":None,
                    "ownership_verified":False,
                    "issue":err.message if err.message in KNOWN_ERRORS else "unverified_service_identity",
                })
        return {
            "scope":"isolated_stage_compose_health_readonly",
            "observed_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
            "capacity":MAX_PROJECTS,
            "project_count":len(results),
            "healthy_projects":sum(x["status"]=="healthy" for x in results),
            "degraded_projects":sum(x["status"]=="degraded" for x in results),
            "unavailable_projects":sum(x["status"]=="unavailable" for x in results),
            "projects":results,
            "production_modified":False,
            "nextcloud_data_inspected":False,
            "migration_allowed":False,
        }
