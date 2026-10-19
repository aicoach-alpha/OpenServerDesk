"""Read-only interpretation of Docker inspect State.Health for owned staging apps.

No Docker calls or HTTP probes occur here. A running container without a
configured healthcheck must never be called healthy by the UI.
"""


def status(state):
    if not isinstance(state, dict):
        return "unknown"
    health = state.get("Health")
    if health is None:
        return "not_configured"
    if not isinstance(health, dict):
        return "unknown"
    value = health.get("Status")
    return value if value in ("healthy", "unhealthy", "starting") else "unknown"


def readiness(running, health_status):
    if not isinstance(running, bool):
        raise ValueError("invalid_stage_running_state")
    if health_status not in ("healthy", "unhealthy", "starting", "not_configured", "unknown"):
        raise ValueError("invalid_stage_health_status")
    if not running:
        return "not_ready"
    return {
        "healthy": "healthcheck_passed",
        "unhealthy": "healthcheck_failed",
        "starting": "checking",
        "not_configured": "not_verified",
        "unknown": "not_verified",
    }[health_status]
