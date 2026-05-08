from __future__ import annotations

from typing import Any

from .paths import STALE_AFTER_SECONDS
from .utils import now_ts
from center.persistence.events import count_by, is_sensor_event

def sensor_summary(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    sensors: dict[str, dict[str, Any]] = {}
    for event in events:
        sensor_id = str(event.get("sensor_id") or event.get("sensor") or "unknown")
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
        item["last_seen"] = event.get("received_at") or event.get("timestamp")
        item["last_event_type"] = event.get("event_type") or event.get("type")
        if item["last_event_type"] == "sensor.enroll":
            item["status"] = "enrolled"
            item["node_hostname"] = event.get("node_hostname", item.get("node_hostname"))
            item["architecture"] = event.get("architecture", item.get("architecture"))
            item["agent_version"] = event.get("agent_version", item.get("agent_version"))
        elif item["last_event_type"] == "sensor.status":
            item["status"] = event.get("status", item["status"])
            item["last_status_seen"] = event.get("received_at") or event.get("timestamp")
            item["applied_version"] = event.get("applied_version", item["applied_version"])
            item["modules"] = event.get("modules", item["modules"])
            item["profile"] = event.get("profile", item.get("profile"))
            item["host"] = event.get("host", item.get("host"))
            item["architecture"] = event.get("architecture", item.get("architecture"))
            item["agent_version"] = event.get("agent_version", item.get("agent_version"))
            item["agent_mode"] = event.get("agent_mode", item.get("agent_mode"))
            item["active_services"] = event.get("active_services", item.get("active_services", []))
            item["listener_errors"] = event.get("listener_errors", item.get("listener_errors", []))
    return sensors


def sensors_payload(policy: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    summaries = sensor_summary(events)
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
        item.setdefault("profile", sensor.get("desired_state", {}).get("profile"))
        last_status_seen = item.get("last_status_seen")
        item["status_age_seconds"] = round(current - float(last_status_seen), 1) if last_status_seen else None
        item["health"] = item.get("status")
        if item.get("status") == "online" and item["status_age_seconds"] is not None and item["status_age_seconds"] > STALE_AFTER_SECONDS:
            item["health"] = "stale"
    return {"sensors": list(summaries.values())}


def overview_payload(policy: dict[str, Any], catalog: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    sensors = sensors_payload(policy, events)["sensors"]
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
