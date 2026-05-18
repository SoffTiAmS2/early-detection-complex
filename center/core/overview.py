from __future__ import annotations

from typing import Any

from .paths import STALE_AFTER_SECONDS
from .utils import now_ts
from center.persistence.events import count_by, is_sensor_event


def newer_timestamp(left: Any, right: Any) -> float | None:
    values = []
    for value in (left, right):
        try:
            if value is not None:
                values.append(float(value))
        except (TypeError, ValueError):
            continue
    return max(values) if values else None

def sensor_summary(
    events: list[dict[str, Any]],
    sensor_states: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    sensors: dict[str, dict[str, Any]] = {sensor_id: dict(state) for sensor_id, state in (sensor_states or {}).items()}
    for event in events:
        sensor_id = str(event.get("sensor_id") or event.get("sensor") or "unknown")
        event_ts = newer_timestamp(None, event.get("received_at") or event.get("timestamp"))
        item = sensors.setdefault(
            sensor_id,
            {
                "sensor_id": sensor_id,
                "events": 0,
                "last_seen": None,
                "last_event_type": None,
                "status": "unknown",
                "applied_version": None,
                "modules": [],
                "last_status_seen": None,
            },
        )
        item["events"] += 1
        previous_last_seen = item.get("last_seen")
        item["last_seen"] = newer_timestamp(previous_last_seen, event_ts)
        event_is_latest = item["last_seen"] == newer_timestamp(previous_last_seen, event_ts) and (
            previous_last_seen is None or item["last_seen"] != previous_last_seen
        )
        if event_is_latest:
            item["last_event_type"] = event.get("event_type") or event.get("type")
        if item["last_event_type"] == "sensor.status":
            previous_status_seen = item.get("last_status_seen")
            latest_status_seen = newer_timestamp(previous_status_seen, event_ts)
            status_is_latest = latest_status_seen == event_ts and event_ts is not None
            item["last_status_seen"] = latest_status_seen
            if not status_is_latest:
                continue
            item["status"] = event.get("status", item["status"])
            item["applied_version"] = event.get("applied_version", item["applied_version"])
            item["config_version"] = event.get("config_version", item.get("config_version"))
            item["modules"] = event.get("modules", item["modules"])
            item["active_profile"] = event.get("active_profile", item.get("active_profile"))
            item["profile"] = event.get("profile", item.get("profile"))
            item["device_type"] = event.get("device_type", item.get("device_type"))
            item["host"] = event.get("host", item.get("host"))
            item["node_hostname"] = event.get("node_hostname", item.get("node_hostname"))
            item["architecture"] = event.get("architecture", item.get("architecture"))
            item["agent_version"] = event.get("agent_version", item.get("agent_version"))
            item["agent_mode"] = event.get("agent_mode", item.get("agent_mode"))
            item["active_services"] = event.get("active_services", item.get("active_services", []))
            item["listener_errors"] = event.get("listener_errors", item.get("listener_errors", []))
    return sensors


def sensors_payload(
    policy: dict[str, Any],
    events: list[dict[str, Any]],
    sensor_states: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    summaries = sensor_summary(events, sensor_states)
    current = now_ts()
    for sensor in policy.get("sensors", []):
        sensor_id = sensor.get("id")
        item = summaries.setdefault(
            sensor_id,
            {
                "sensor_id": sensor_id,
                "events": 0,
                "last_seen": None,
                "last_event_type": None,
                "status": "never_seen",
                "applied_version": None,
                "modules": [],
                "last_status_seen": None,
            },
        )
        item.setdefault("host", sensor.get("host"))
        item.setdefault("architecture", sensor.get("architecture"))
        desired = sensor.get("desired_state", {}) if isinstance(sensor.get("desired_state"), dict) else {}
        item.setdefault("active_profile", sensor.get("active_profile") or desired.get("active_profile") or desired.get("profile"))
        item.setdefault("profile", desired.get("profile"))
        item.setdefault("device_type", desired.get("device_type"))
        item.setdefault("config_version", desired.get("config_version"))
        item.setdefault("open_ports", [port.get("port") for port in desired.get("exposed_ports", []) if isinstance(port, dict)])
        last_status_seen = item.get("last_status_seen")
        item["status_age_seconds"] = round(current - float(last_status_seen), 1) if last_status_seen else None
        item["health"] = item.get("status")
        if item.get("status") == "online" and item["status_age_seconds"] is not None and item["status_age_seconds"] > STALE_AFTER_SECONDS:
            item["health"] = "stale"
        item["provisioning"] = provisioning_state(sensor, item)
    return {"sensors": list(summaries.values())}


def provisioning_state(policy_sensor: dict[str, Any], live: dict[str, Any]) -> dict[str, Any]:
    base = policy_sensor.get("provisioning") if isinstance(policy_sensor.get("provisioning"), dict) else {}
    state = dict(base)
    listener_errors = live.get("listener_errors") if isinstance(live.get("listener_errors"), list) else []
    if listener_errors:
        active_count = len(live.get("active_services") if isinstance(live.get("active_services"), list) else [])
        if active_count:
            state.update(
                {
                    "status": "degraded",
                    "stage": "runtime_partial",
                    "progress": 90,
                    "message": f"Agent online, активных сервисов: {active_count}, ошибок runtime: {len(listener_errors)}.",
                }
            )
            return state
        state.update(
            {
                "status": "error",
                "stage": "runtime_errors",
                "progress": 90,
                "message": f"Agent online, но runtime сообщил ошибки: {len(listener_errors)}.",
            }
        )
    elif live.get("health") == "online":
        state.update(
            {
                "status": "completed",
                "stage": "agent_online",
                "progress": 100,
                "message": "Sensor-agent синхронизировался и отправляет актуальный status.",
            }
        )
    elif live.get("health") == "stale":
        state.update(
            {
                "status": "stale",
                "stage": "heartbeat_stale",
                "progress": 75,
                "message": "Сенсор был online, но heartbeat устарел.",
            }
        )
    elif live.get("last_status_seen"):
        state.update(
            {
                "status": "processing",
                "stage": "agent_seen",
                "progress": 85,
                "message": "Agent был зарегистрирован центром, ожидается свежий runtime status.",
            }
        )
    else:
        state.update(
            {
                "status": state.get("status") or "waiting_agent",
                "stage": state.get("stage") or "policy_saved",
                "progress": int(state.get("progress") or 45),
                "message": state.get("message") or "Сенсор есть в политике, центр ожидает первый sync от agent.",
            }
        )
    return state


def overview_payload(
    policy: dict[str, Any],
    catalog: dict[str, Any],
    events: list[dict[str, Any]],
    sensor_states: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    sensors = sensors_payload(policy, events, sensor_states)["sensors"]
    online = sum(1 for sensor in sensors if sensor.get("status") == "online")
    healthy = sum(1 for sensor in sensors if sensor.get("health") == "online")
    stale = sum(1 for sensor in sensors if sensor.get("health") == "stale")
    suspicious_events = [event for event in events if not is_sensor_event(event)]
    planned_modules = sorted(
        {
            module.get("id")
            for sensor in policy.get("sensors", [])
            for module in sensor.get("desired_state", {}).get("modules", [])
            if isinstance(module, dict) and module.get("enabled", True) is not False
        }
    )
    return {
        "project": "distributed early-detection complex",
        "site": policy.get("site", {}),
        "policy_version": int(policy.get("version", 1)),
        "sensor_count": len(sensors),
        "online_sensors": online,
        "healthy_sensors": healthy,
        "stale_sensors": stale,
        "event_count_window": len(events),
        "suspicious_event_count_window": len(suspicious_events),
        "severity_counts": count_by(suspicious_events, "severity"),
        "module_counts": count_by(suspicious_events, "module"),
        "service_counts": count_by(suspicious_events, "service"),
        "event_type_counts": count_by(suspicious_events, "event_type"),
        "catalog_modules": [module.get("id") for module in catalog.get("modules", [])],
        "planned_modules": planned_modules,
        "recent_suspicious_events": suspicious_events[-10:],
        "sensors": sensors,
    }
