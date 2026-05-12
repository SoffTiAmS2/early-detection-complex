from __future__ import annotations

from typing import Any

from center.core.policy import desired_state
from center.core.utils import now_ts


def sensor_status_event(
    sensor_id: str,
    payload: dict[str, Any],
    desired: dict[str, Any] | None,
) -> dict[str, Any]:
    """Convert a sensor sync payload into the status event stored by the center."""

    facts = payload.get("facts") if isinstance(payload.get("facts"), dict) else {}
    status = payload.get("status") if isinstance(payload.get("status"), dict) else {}
    return {
        "event_type": "sensor.status",
        "timestamp": payload.get("timestamp") or now_ts(),
        "sensor_id": sensor_id,
        "status": status.get("state", "online"),
        "agent_version": payload.get("agent_version"),
        "agent_mode": status.get("mode"),
        "applied_version": status.get("applied_version"),
        "profile": desired.get("profile") if desired else status.get("profile"),
        "host": desired.get("host") if desired else status.get("host"),
        "node_hostname": facts.get("hostname"),
        "architecture": facts.get("architecture") or (desired.get("architecture") if desired else None),
        "modules": status.get("modules", []),
        "active_services": status.get("active_services", []),
        "listener_errors": status.get("listener_errors", []),
    }


def sensor_sync(
    policy: dict[str, Any],
    catalog: dict[str, Any],
    sensor_id: str,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = desired_state(policy, catalog, sensor_id)
    return sensor_status_event(sensor_id, payload, state), sensor_sync_response(policy, state)


def sensor_sync_response(policy: dict[str, Any], state: dict[str, Any] | None) -> dict[str, Any]:
    response: dict[str, Any] = {
        "registered": bool(state),
        "policy_version": int(policy.get("version", 1)),
    }
    if state:
        response["desired_state"] = state
    else:
        response["warning"] = "sensor is not present in policy"
    return response
