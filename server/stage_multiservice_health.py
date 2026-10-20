"""Conservative project readiness derived from already owner-verified Docker state.

This pure helper never inspects Docker itself or probes application networks.
"""
from stage_container_health import readiness as container_readiness


def assess(services, completed_names=()):
    completed_names=set(completed_names)
    if not isinstance(services, list) or not services:
        raise ValueError("invalid_compiled_health_services")
    checked = []
    names = set()
    for service in services:
        if not isinstance(service, dict):
            raise ValueError("invalid_compiled_service_health")
        name, running, health = (
            service.get("name"), service.get("running"), service.get("health"))
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("invalid_compiled_service_name")
        if not isinstance(running, bool) or health not in (None, "healthy", "unhealthy", "starting"):
            raise ValueError("invalid_compiled_service_health")
        names.add(name)
        completed=(name in completed_names and not running and
                   service.get("status")=="exited" and service.get("exit_code")==0)
        checked.append({
            "name": name, "running": running, "completed":completed,
            "health_status": health if health is not None else "not_configured",
            "readiness": ("init_completed" if completed else container_readiness(
                running, health if health is not None else "not_configured")),
        })
    total = len(checked)
    running_count = sum(s["running"] for s in checked)
    unhealthy = sum(s["running"] and s["health_status"] == "unhealthy" for s in checked)
    starting = sum(s["running"] and s["health_status"] == "starting" for s in checked)
    unverified = sum(s["running"] and s["health_status"] == "not_configured" for s in checked)
    stopped = total - running_count
    finished = sum(s["completed"] for s in checked)
    incomplete = total-running_count-finished
    lifecycle = ("running" if running_count+finished == total
                 else "stopped" if running_count == 0 and not finished
                 else "partially_running")
    if incomplete:
        readiness = "not_ready"
        health_status = "unhealthy" if unhealthy else "unknown"
    elif unhealthy:
        readiness, health_status = "healthcheck_failed", "unhealthy"
    elif starting:
        readiness, health_status = "checking", "starting"
    elif unverified:
        readiness = "not_verified"
        health_status = "not_configured" if unverified == total else "unknown"
    else:
        readiness, health_status = "healthcheck_passed", "healthy"
    return {
        "lifecycle": lifecycle, "readiness": readiness,
        "health_status": health_status,
        "partial_failure": bool((incomplete and (running_count or finished)) or unhealthy),
        "counts": {
            "total": total, "running": running_count, "stopped": stopped,
            "unhealthy": unhealthy, "starting": starting, "unverified": unverified,
            "completed_init": finished,
        },
        "services": checked,
    }
