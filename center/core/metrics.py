from __future__ import annotations

from typing import Any

from center.core.overview import sensors_payload
from center.persistence.events import count_by, is_sensor_event


def prom_escape(value: Any) -> str:
    return str(value if value is not None else "unknown").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def labels(**items: Any) -> str:
    return ",".join(f'{key}="{prom_escape(value)}"' for key, value in items.items())


def prometheus_metrics(policy: dict[str, Any], events: list[dict[str, Any]]) -> str:
    suspicious = [event for event in events if not is_sensor_event(event)]
    sensors = sensors_payload(policy, events)["sensors"]
    lines = [
        "# HELP edc_events_window_total Events currently visible in the center query window.",
        "# TYPE edc_events_window_total counter",
        f"edc_events_window_total {len(events)}",
        "# HELP edc_suspicious_events_window_total Honeypot events in the current center query window.",
        "# TYPE edc_suspicious_events_window_total counter",
        f"edc_suspicious_events_window_total {len(suspicious)}",
        "# HELP edc_sensor_online Sensor online state derived from last sync.",
        "# TYPE edc_sensor_online gauge",
    ]
    for sensor in sensors:
        value = 1 if sensor.get("health") == "online" else 0
        lines.append(f"edc_sensor_online{{{labels(sensor_id=sensor.get('sensor_id'),host=sensor.get('host'))}}} {value}")
        age = sensor.get("status_age_seconds")
        if age is not None:
            lines.append(f"edc_sensor_status_age_seconds{{{labels(sensor_id=sensor.get('sensor_id'))}}} {age}")

    for key, metric in (
        ("sensor_id", "edc_events_by_sensor_window_total"),
        ("module", "edc_events_by_module_window_total"),
        ("service", "edc_events_by_service_window_total"),
        ("severity", "edc_events_by_severity_window_total"),
        ("event_type", "edc_events_by_type_window_total"),
    ):
        lines.extend([f"# TYPE {metric} counter"])
        for value, count in count_by(suspicious, key).items():
            lines.append(f"{metric}{{{labels(**{key: value})}}} {count}")
    return "\n".join(lines) + "\n"
