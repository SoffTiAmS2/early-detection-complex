#!/usr/bin/env python3
"""Control-plane MVP for the distributed early-detection complex.

The server intentionally uses only the Python standard library. It exposes the
core HoneySens-like loop: sensors enroll, poll desired state and post events.
"""

from __future__ import annotations

import argparse
import html
import json
import sqlite3
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "catalog" / "honeypots.json"
DEFAULT_POLICY = ROOT / "config" / "site.example.json"
DEFAULT_STORE = ROOT / "var" / "center" / "events.sqlite3"
MAX_EVENT_LIMIT = 1000
STALE_AFTER_SECONDS = 45


def now_ts() -> float:
    return time.time()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def bump_policy_version(policy: dict[str, Any]) -> dict[str, Any]:
    updated = json.loads(json.dumps(policy))
    try:
        version = int(updated.get("version", 0))
    except (TypeError, ValueError):
        version = 0
    updated["version"] = version + 1
    updated["updated_at"] = now_ts()
    return updated


def connect_store(store: Path) -> sqlite3.Connection:
    store.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(store)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            received_at REAL NOT NULL,
            timestamp REAL,
            event_type TEXT NOT NULL,
            sensor_id TEXT,
            module TEXT,
            service TEXT,
            severity TEXT,
            src_ip TEXT,
            src_port INTEGER,
            dst_port INTEGER,
            raw_sample TEXT,
            raw_event TEXT NOT NULL
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_received_at ON events(received_at)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_sensor_id ON events(sensor_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_module ON events(module)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_service ON events(service)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type)")
    return connection


def write_event(store: Path, event: dict[str, Any]) -> None:
    stored = json.loads(json.dumps(event, ensure_ascii=False))
    stored.setdefault("received_at", now_ts())
    stored.setdefault("event_type", stored.get("type", "sensor.event"))
    raw_event = json.dumps(stored, ensure_ascii=False, sort_keys=True)
    with connect_store(store) as connection:
        connection.execute(
            """
            INSERT INTO events (
                received_at, timestamp, event_type, sensor_id, module, service, severity,
                src_ip, src_port, dst_port, raw_sample, raw_event
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                float(stored.get("received_at") or now_ts()),
                stored.get("timestamp"),
                str(stored.get("event_type") or "sensor.event"),
                stored.get("sensor_id") or stored.get("sensor"),
                stored.get("module"),
                stored.get("service"),
                stored.get("severity"),
                stored.get("src_ip"),
                stored.get("src_port"),
                stored.get("dst_port"),
                stored.get("raw_sample") or stored.get("message"),
                raw_event,
            ),
        )


def read_events(store: Path, limit: int) -> list[dict[str, Any]]:
    if not store.exists():
        return []
    with connect_store(store) as connection:
        rows = connection.execute(
            """
            SELECT id, received_at, timestamp, event_type, sensor_id, module, service, severity,
                   src_ip, src_port, dst_port, raw_sample, raw_event
            FROM events
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, min(limit, MAX_EVENT_LIMIT)),),
        ).fetchall()
    events: list[dict[str, Any]] = []
    for row in reversed(rows):
        try:
            raw_event = json.loads(row["raw_event"])
        except json.JSONDecodeError:
            raw_event = {"event_type": "parse_error", "raw": row["raw_event"]}
        event = dict(raw_event) if isinstance(raw_event, dict) else {"event_type": row["event_type"]}
        event.update(
            {
                "_event_id": row["id"],
                "received_at": row["received_at"],
                "event_type": row["event_type"],
                "sensor_id": row["sensor_id"] or event.get("sensor_id") or event.get("sensor"),
                "module": row["module"] or event.get("module"),
                "service": row["service"] or event.get("service"),
                "severity": row["severity"] or event.get("severity"),
                "src_ip": row["src_ip"] or event.get("src_ip"),
                "src_port": row["src_port"] if row["src_port"] is not None else event.get("src_port"),
                "dst_port": row["dst_port"] if row["dst_port"] is not None else event.get("dst_port"),
                "raw_sample": row["raw_sample"] or event.get("raw_sample"),
                "raw_event": raw_event,
            }
        )
        events.append(event)
    return events


def is_sensor_event(event: dict[str, Any]) -> bool:
    return str(event.get("event_type", "")).startswith("sensor.")


def count_by(events: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        value = str(event.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def event_matches(event: dict[str, Any], filters: dict[str, str]) -> bool:
    for key, expected in filters.items():
        if not expected:
            continue
        if str(event.get(key, "")) != expected:
            return False
    return True


def filter_events(events: list[dict[str, Any]], params: dict[str, list[str]]) -> list[dict[str, Any]]:
    filters = {
        "sensor_id": params.get("sensor_id", [""])[0],
        "module": params.get("module", [""])[0],
        "service": params.get("service", [""])[0],
        "severity": params.get("severity", [""])[0],
        "event_type": params.get("event_type", [""])[0],
    }
    suspicious_only = params.get("suspicious", ["0"])[0] in {"1", "true", "yes"}
    filtered = []
    for event in events:
        if suspicious_only and is_sensor_event(event):
            continue
        if event_matches(event, filters):
            filtered.append(event)
    return filtered


def modules_by_id(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {module["id"]: module for module in catalog.get("modules", [])}


def services_by_id(module: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {service["id"]: service for service in module.get("services", [])}


def settings_schema_by_key(module: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {field["key"]: field for field in module.get("config_schema", []) if isinstance(field, dict) and field.get("key")}


def validate_module_settings(sensor_id: str, module_id: str, settings: Any, catalog_module: dict[str, Any]) -> list[str]:
    if settings is None:
        return []
    if not isinstance(settings, dict):
        return [f"{sensor_id}: {module_id}: settings must be an object"]
    errors: list[str] = []
    schema = settings_schema_by_key(catalog_module)
    for key, value in settings.items():
        field = schema.get(str(key))
        if not field:
            continue
        field_type = field.get("type", "string")
        if field_type in {"string", "textarea", "list"}:
            if not isinstance(value, (str, list)):
                errors.append(f"{sensor_id}: {module_id}: setting {key} must be text")
            continue
        if field_type == "boolean":
            if not isinstance(value, bool):
                errors.append(f"{sensor_id}: {module_id}: setting {key} must be boolean")
            continue
        if field_type == "integer":
            try:
                numeric = int(value)
            except (TypeError, ValueError):
                errors.append(f"{sensor_id}: {module_id}: setting {key} must be integer")
                continue
            if "min" in field and numeric < int(field["min"]):
                errors.append(f"{sensor_id}: {module_id}: setting {key} must be >= {field['min']}")
            if "max" in field and numeric > int(field["max"]):
                errors.append(f"{sensor_id}: {module_id}: setting {key} must be <= {field['max']}")
            continue
        if field_type == "select":
            options = [str(item) for item in field.get("options", [])]
            if options and str(value) not in options:
                errors.append(f"{sensor_id}: {module_id}: setting {key} must be one of {', '.join(options)}")
    return errors


def policy_errors(policy: Any, catalog: Any) -> list[str]:
    """Validate the site policy before the center publishes desired state."""

    errors: list[str] = []
    if not isinstance(catalog, dict):
        return ["catalog must be an object"]
    if not isinstance(policy, dict):
        return ["policy must be an object"]

    module_index: dict[str, dict[str, Any]] = {}
    for module in catalog.get("modules", []):
        if not isinstance(module, dict):
            errors.append("catalog module must be an object")
            continue
        module_id = module.get("id")
        if not isinstance(module_id, str) or not module_id:
            errors.append("catalog module id must be a non-empty string")
            continue
        if module_id in module_index:
            errors.append(f"duplicate catalog module: {module_id}")
        module_index[module_id] = module

    sensors = policy.get("sensors")
    if not isinstance(sensors, list) or not sensors:
        errors.append("policy must contain at least one sensor")
        return errors

    seen_sensors: set[str] = set()
    for sensor in sensors:
        if not isinstance(sensor, dict):
            errors.append("sensor must be an object")
            continue
        sensor_id = sensor.get("id")
        if not isinstance(sensor_id, str) or not sensor_id:
            errors.append("sensor id must be a non-empty string")
            continue
        if sensor_id in seen_sensors:
            errors.append(f"duplicate sensor id: {sensor_id}")
        seen_sensors.add(sensor_id)

        desired = sensor.get("desired_state")
        if not isinstance(desired, dict):
            errors.append(f"{sensor_id}: desired_state must be an object")
            continue
        modules = desired.get("modules")
        if not isinstance(modules, list):
            errors.append(f"{sensor_id}: desired_state.modules must be a list")
            continue

        used_ports: dict[int, str] = {}
        for item in modules:
            if not isinstance(item, dict):
                errors.append(f"{sensor_id}: module must be an object")
                continue
            module_id = item.get("id")
            catalog_module = module_index.get(str(module_id))
            if not catalog_module:
                errors.append(f"{sensor_id}: unknown module: {module_id}")
                continue
            service_index = services_by_id(catalog_module)
            services = item.get("services")
            if not isinstance(services, list):
                errors.append(f"{sensor_id}: {module_id}: services must be a list")
                continue
            errors.extend(validate_module_settings(sensor_id, str(module_id), item.get("settings", {}), catalog_module))
            for service in services:
                if not isinstance(service, dict):
                    errors.append(f"{sensor_id}: {module_id}: service must be an object")
                    continue
                service_id = service.get("id")
                catalog_service = service_index.get(str(service_id))
                if not catalog_service:
                    errors.append(f"{sensor_id}: {module_id}: unknown service: {service_id}")
                    continue
                try:
                    host_port = int(service.get("host_port", catalog_service.get("default_host_port")))
                except (TypeError, ValueError):
                    errors.append(f"{sensor_id}: {module_id}/{service_id}: host_port must be an integer")
                    continue
                if not 1 <= host_port <= 65535:
                    errors.append(f"{sensor_id}: {module_id}/{service_id}: host_port out of range")
                    continue
                if item.get("enabled", True) is not False and service.get("enabled", True) is not False:
                    owner = used_ports.get(host_port)
                    if owner:
                        errors.append(f"{sensor_id}: port conflict tcp/{host_port}: {owner} and {module_id}/{service_id}")
                    used_ports[host_port] = f"{module_id}/{service_id}"
    return errors


def find_sensor(policy: dict[str, Any], sensor_id: str) -> dict[str, Any] | None:
    for sensor in policy.get("sensors", []):
        if sensor.get("id") == sensor_id:
            return sensor
    return None


def ensure_desired_module(sensor: dict[str, Any], catalog_module: dict[str, Any]) -> dict[str, Any]:
    desired = sensor.setdefault("desired_state", {})
    modules = desired.setdefault("modules", [])
    for module in modules:
        if module.get("id") == catalog_module.get("id"):
            return module
    module = {
        "id": catalog_module["id"],
        "enabled": False,
        "services": [
            {"id": service["id"], "enabled": True, "host_port": service.get("default_host_port", service.get("container_port"))}
            for service in catalog_module.get("services", [])
        ],
        "settings": {
            field["key"]: field.get("default", "")
            for field in catalog_module.get("config_schema", [])
            if isinstance(field, dict) and field.get("key")
        },
    }
    modules.append(module)
    return module


def ensure_desired_service(module: dict[str, Any], catalog_service: dict[str, Any]) -> dict[str, Any]:
    services = module.setdefault("services", [])
    for service in services:
        if service.get("id") == catalog_service.get("id"):
            return service
    service = {
        "id": catalog_service["id"],
        "enabled": True,
        "host_port": catalog_service.get("default_host_port", catalog_service.get("container_port")),
    }
    services.append(service)
    return service


def desired_state(policy: dict[str, Any], catalog: dict[str, Any], sensor_id: str) -> dict[str, Any] | None:
    sensor = find_sensor(policy, sensor_id)
    if not sensor:
        return None
    module_index = modules_by_id(catalog)
    desired = sensor.get("desired_state", {})
    planned_modules = []
    for item in desired.get("modules", []):
        module_id = item.get("id")
        catalog_module = module_index.get(module_id)
        if not catalog_module:
            continue
        service_index = services_by_id(catalog_module)
        planned_services = []
        for service in item.get("services", []):
            if service.get("enabled", True) is False:
                continue
            service_id = service.get("id")
            catalog_service = service_index.get(service_id)
            if not catalog_service:
                continue
            planned_services.append(
                {
                    **catalog_service,
                    "id": service_id,
                    "host_port": service.get("host_port", catalog_service.get("default_host_port")),
                }
            )
        planned_modules.append(
            {
                "id": module_id,
                "title": catalog_module.get("title"),
                "enabled": item.get("enabled", True) is not False,
                "status": catalog_module.get("status"),
                "runtime": catalog_module.get("runtime"),
                "resource_class": catalog_module.get("resource_class"),
                "settings": item.get("settings", {}),
                "services": planned_services,
            }
        )
    return {
        "sensor_id": sensor_id,
        "version": int(policy.get("version", 1)),
        "site": policy.get("site", {}),
        "host": sensor.get("host"),
        "architecture": sensor.get("architecture"),
        "profile": desired.get("profile"),
        "persona": desired.get("persona", {}),
        "modules": planned_modules,
    }


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


def render_dashboard(policy: dict[str, Any]) -> str:
    site_name = html.escape(str(policy.get("site", {}).get("name", "EDC")))
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{site_name} - Early Detection Center</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #17202a;
      --muted: #637083;
      --line: #d9dee7;
      --ok: #147a3d;
      --warn: #a15c00;
      --bad: #b42318;
      --info: #075985;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.45; }}
    header {{ padding: 22px 28px 16px; border-bottom: 1px solid var(--line); background: #ffffff; position: sticky; top: 0; z-index: 2; }}
    h1 {{ margin: 0; font-size: 22px; font-weight: 750; }}
    main {{ padding: 22px 28px 36px; max-width: 1440px; margin: 0 auto; }}
    h2 {{ margin: 0 0 10px; font-size: 16px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ text-align: left; padding: 8px 6px; border-top: 1px solid var(--line); vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 650; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }}
    a.button {{ display: inline-block; border: 1px solid #0f766e; background: #0f766e; color: white; border-radius: 6px; padding: 7px 10px; text-decoration: none; }}
    .sub, .muted {{ color: var(--muted); }}
    .grid {{ display: grid; grid-template-columns: repeat(5, minmax(140px, 1fr)); gap: 12px; margin-bottom: 18px; }}
    .layout {{ display: grid; grid-template-columns: 1.1fr 1.9fr; gap: 14px; align-items: start; }}
    .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; overflow: hidden; }}
    .metric .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    .metric .value {{ font-size: 28px; font-weight: 780; margin-top: 2px; }}
    .manager {{ margin-top: 14px; }}
    .manager-head {{ display: flex; justify-content: space-between; align-items: end; gap: 12px; margin-bottom: 10px; }}
    select {{ border: 1px solid var(--line); border-radius: 6px; padding: 7px 8px; font: inherit; background: #fff; }}
    .honeypots {{ display: grid; grid-template-columns: repeat(5, minmax(180px, 1fr)); gap: 10px; }}
    .honeypot {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fbfcfe; }}
    .honeypot-head {{ display: flex; justify-content: space-between; gap: 8px; align-items: center; margin-bottom: 6px; }}
    .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--line); background: #f8fafc; }}
    .ok {{ color: var(--ok); }}
    .warn {{ color: var(--warn); }}
    .bad {{ color: var(--bad); }}
    .info {{ color: var(--info); }}
    .counts {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 4px; }}
    .event {{ border-top: 1px solid var(--line); padding: 10px 0; }}
    .event:first-child {{ border-top: 0; }}
    .event-head {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
    .sample {{ margin-top: 6px; color: var(--muted); white-space: pre-wrap; overflow-wrap: anywhere; max-height: 96px; overflow: auto; }}
    @media (max-width: 1100px) {{ .grid, .honeypots {{ grid-template-columns: repeat(2, minmax(150px, 1fr)); }} .layout {{ grid-template-columns: 1fr; }} }}
    @media (max-width: 640px) {{ header, main {{ padding-left: 16px; padding-right: 16px; }} .grid, .honeypots {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Early Detection Center</h1>
    <div class="sub">{site_name} · distributed suspicious network activity detection</div>
  </header>
  <main>
    <section class="grid" id="metrics"></section>
    <section class="layout">
      <div class="panel">
        <h2>Сенсоры</h2>
        <div id="sensors"></div>
      </div>
      <div class="panel">
        <h2>События раннего обнаружения</h2>
        <div id="counts"></div>
        <div id="events"></div>
      </div>
    </section>
    <section class="panel manager">
      <div class="manager-head">
        <div>
          <h2>Honeypot modules</h2>
          <div class="muted">Здесь только модули, реально описанные в текущей политике выбранного сенсора.</div>
        </div>
        <label class="muted">Sensor<br><select id="sensorSelect"></select></label>
      </div>
      <div class="honeypots" id="honeypots"></div>
    </section>
  </main>
  <script>
    let managedSensorId = new URLSearchParams(location.search).get('sensor_id') || 'sensor1';
    const el = (id) => document.getElementById(id);
    const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }}[ch]));
    const age = (ts) => ts ? Math.round(Date.now() / 1000 - ts) + 's ago' : 'never';
    function metric(label, value, cls='') {{ return `<div class="panel metric"><div class="label">${{esc(label)}}</div><div class="value ${{cls}}">${{esc(value)}}</div></div>`; }}
    function renderCounts(title, data) {{
      const parts = Object.entries(data || {{}}).map(([k, v]) => `<span class="pill">${{esc(k)}}: ${{esc(v)}}</span>`);
      return `<div class="muted">${{esc(title)}}</div><div class="counts">${{parts.join('') || '<span class="muted">none</span>'}}</div>`;
    }}
    function renderSensor(sensor) {{
      const healthClass = sensor.health === 'online' ? 'ok' : (sensor.health === 'stale' ? 'warn' : 'bad');
      const services = (sensor.active_services || []).map((s) => `${{s.module}}/${{s.service}}:${{s.host_port}}`).join(', ');
      return `<tr>
        <td><strong>${{esc(sensor.sensor_id)}}</strong><br><span class="muted">${{esc(sensor.host)}} · ${{esc(sensor.node_hostname || '')}}</span></td>
        <td><span class="${{healthClass}}">${{esc(sensor.health || sensor.status)}}</span><br><span class="muted">${{esc(sensor.agent_mode || '')}}</span></td>
        <td>${{esc(sensor.events)}}<br><span class="muted">${{age(sensor.last_seen)}}</span></td>
        <td>${{esc((sensor.modules || []).filter((m) => m.status === 'running').length)}} running<br><span class="muted">${{esc(services)}}</span></td>
      </tr>`;
    }}
    function renderEvent(event) {{
      const severityClass = event.severity === 'high' ? 'bad' : (event.severity === 'medium' ? 'warn' : 'info');
      return `<div class="event"><div class="event-head">
        <span class="pill ${{severityClass}}">${{esc(event.severity || 'unknown')}}</span>
        <strong>${{esc(event.event_type)}}</strong>
        <span>${{esc(event.module)}}/${{esc(event.service)}}:${{esc(event.dst_port)}}</span>
        <span class="muted">from ${{esc(event.src_ip)}} · ${{age(event.received_at || event.timestamp)}}</span>
      </div><code class="sample">${{esc(event.raw_sample || '')}}</code></div>`;
    }}
    function renderHoneypots(policy, catalog, sensors) {{
      const sensorSelect = el('sensorSelect');
      sensorSelect.innerHTML = (policy.sensors || []).map((sensor) => `<option value="${{esc(sensor.id)}}" ${{sensor.id === managedSensorId ? 'selected' : ''}}>${{esc(sensor.id)}} · ${{esc(sensor.host || '')}}</option>`).join('');
      const sensorPolicy = (policy.sensors || []).find((sensor) => sensor.id === managedSensorId);
      const desiredModules = sensorPolicy?.desired_state?.modules || [];
      const live = (sensors || []).find((sensor) => sensor.sensor_id === managedSensorId);
      el('honeypots').innerHTML = desiredModules.map((desired) => {{
        const cat = (catalog.modules || []).find((module) => module.id === desired.id) || desired;
        const liveModule = (live?.modules || []).find((module) => module.id === desired.id);
        const services = (desired.services || []).filter((service) => service.enabled !== false).map((service) => `${{service.id}}:${{service.host_port}}`).join(', ');
        const enabled = desired.enabled !== false;
        const state = liveModule?.status || (enabled ? 'pending' : 'disabled');
        const stateClass = state === 'running' ? 'ok' : (state === 'disabled' ? 'muted' : 'warn');
        return `<div class="honeypot">
          <div class="honeypot-head"><strong>${{esc(cat.title || desired.id)}}</strong><span class="pill ${{stateClass}}">${{esc(state)}}</span></div>
          <div class="muted">${{esc(cat.purpose || '')}}</div>
          <p><code>${{esc(desired.id)}}</code></p>
          <p class="muted">${{esc(services || 'no enabled services')}}</p>
          <a class="button" href="/honeypots/${{encodeURIComponent(desired.id)}}?sensor_id=${{encodeURIComponent(managedSensorId)}}">Настроить</a>
        </div>`;
      }}).join('');
    }}
    el('sensorSelect').addEventListener('change', () => {{
      managedSensorId = el('sensorSelect').value;
      const url = new URL(location.href);
      url.searchParams.set('sensor_id', managedSensorId);
      history.replaceState(null, '', url);
      refresh();
    }});
    async function refresh() {{
      const [overviewResponse, policyResponse, catalogResponse] = await Promise.all([
        fetch('/api/overview', {{ cache: 'no-store' }}),
        fetch('/api/policy', {{ cache: 'no-store' }}),
        fetch('/api/modules', {{ cache: 'no-store' }})
      ]);
      const data = await overviewResponse.json();
      const policy = (await policyResponse.json()).policy;
      const catalog = await catalogResponse.json();
      el('metrics').innerHTML = [
        metric('Sensors', `${{data.healthy_sensors}}/${{data.sensor_count}}`, data.healthy_sensors === data.sensor_count ? 'ok' : 'warn'),
        metric('Suspicious Events', data.suspicious_event_count_window),
        metric('High Severity', (data.severity_counts || {{}}).high || 0, 'bad'),
        metric('Active Modules', (data.planned_modules || []).length),
        metric('Policy Version', data.policy_version)
      ].join('');
      el('counts').innerHTML = renderCounts('Severity', data.severity_counts) + renderCounts('Modules', data.module_counts) + renderCounts('Services', data.service_counts);
      el('sensors').innerHTML = `<table><thead><tr><th>Sensor</th><th>Health</th><th>Events</th><th>Services</th></tr></thead><tbody>${{(data.sensors || []).map(renderSensor).join('')}}</tbody></table>`;
      el('events').innerHTML = (data.recent_suspicious_events || []).slice().reverse().map(renderEvent).join('') || '<p class="muted">No suspicious events yet.</p>';
      renderHoneypots(policy, catalog, data.sensors);
    }}
    refresh();
    setInterval(refresh, 3000);
  </script>
</body>
</html>"""


def render_honeypot_page(policy: dict[str, Any], catalog: dict[str, Any], sensor_id: str, module_id: str) -> str | None:
    catalog_module = modules_by_id(catalog).get(module_id)
    if not catalog_module:
        return None
    title = html.escape(str(catalog_module.get("title") or module_id))
    safe_module_id = html.escape(module_id)
    safe_sensor_id = html.escape(sensor_id)
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} - Honeypot Config</title>
  <style>
    :root {{ color-scheme: light; --bg: #f6f7f9; --panel: #ffffff; --text: #17202a; --muted: #637083; --line: #d9dee7; --ok: #147a3d; --bad: #b42318; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.45; }}
    header {{ padding: 18px 28px; border-bottom: 1px solid var(--line); background: #fff; position: sticky; top: 0; z-index: 2; }}
    main {{ padding: 22px 28px 36px; max-width: 1100px; margin: 0 auto; }}
    h1 {{ margin: 4px 0 0; font-size: 22px; }}
    h2 {{ margin: 0 0 10px; font-size: 16px; }}
    a {{ color: #0f766e; }}
    button {{ border: 1px solid #0f766e; background: #0f766e; color: white; border-radius: 6px; padding: 8px 12px; font: inherit; cursor: pointer; }}
    button.secondary {{ color: var(--text); background: #fff; border-color: var(--line); }}
    label {{ display: block; font-size: 13px; color: var(--muted); }}
    input, select, textarea {{ width: 100%; border: 1px solid var(--line); border-radius: 6px; padding: 7px 8px; font: inherit; background: #fff; }}
    input[type="checkbox"] {{ width: auto; margin-right: 6px; }}
    textarea {{ min-height: 96px; resize: vertical; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ text-align: left; padding: 8px 6px; border-top: 1px solid var(--line); vertical-align: middle; }}
    th {{ color: var(--muted); font-weight: 650; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }}
    .muted {{ color: var(--muted); }}
    .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; margin-bottom: 14px; overflow: hidden; }}
    .form-grid {{ display: grid; grid-template-columns: repeat(2, minmax(220px, 1fr)); gap: 10px; }}
    .field {{ display: flex; flex-direction: column; gap: 4px; }}
    .field.wide {{ grid-column: 1 / -1; }}
    .help {{ color: var(--muted); font-size: 12px; }}
    .actions {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
    .ok {{ color: var(--ok); }}
    .bad {{ color: var(--bad); }}
    @media (max-width: 760px) {{ header, main {{ padding-left: 16px; padding-right: 16px; }} .form-grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <a href="/">← Dashboard</a>
    <h1>{title}</h1>
    <div class="muted">sensor <code>{safe_sensor_id}</code> · module <code>{safe_module_id}</code></div>
  </header>
  <main>
    <section class="panel">
      <h2>Модуль</h2>
      <p class="muted" id="modulePurpose"></p>
      <label><input id="moduleEnabled" type="checkbox"> Включить honeypot на сенсоре</label>
    </section>
    <section class="panel">
      <h2>Сервисы и порты</h2>
      <div id="services"></div>
    </section>
    <section class="panel">
      <h2>Settings</h2>
      <div class="form-grid" id="settings"></div>
    </section>
    <section class="panel">
      <div class="actions">
        <button id="save">Сохранить конфигурацию</button>
        <button class="secondary" id="reload">Сбросить изменения</button>
        <span class="muted" id="status"></span>
      </div>
    </section>
    <section class="panel">
      <h2>Последние события этого honeypot</h2>
      <div id="events"></div>
    </section>
  </main>
  <script>
    const moduleId = '{safe_module_id}';
    const sensorId = '{safe_sensor_id}';
    let policy = null;
    let catalogModule = null;
    let desiredModule = null;
    const el = (id) => document.getElementById(id);
    const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }}[ch]));
    const age = (ts) => ts ? Math.round(Date.now() / 1000 - ts) + 's ago' : 'never';
    function sensorPolicy() {{ return (policy?.sensors || []).find((sensor) => sensor.id === sensorId); }}
    function ensureDesired() {{
      const sensor = sensorPolicy();
      sensor.desired_state ||= {{}};
      sensor.desired_state.modules ||= [];
      desiredModule = sensor.desired_state.modules.find((item) => item.id === moduleId);
      if (!desiredModule) {{
        desiredModule = {{ id: moduleId, enabled: false, services: [], settings: {{}} }};
        sensor.desired_state.modules.push(desiredModule);
      }}
      desiredModule.services ||= [];
      desiredModule.settings ||= {{}};
      for (const service of catalogModule.services || []) {{
        if (!desiredModule.services.find((item) => item.id === service.id)) {{
          desiredModule.services.push({{ id: service.id, enabled: true, host_port: service.default_host_port || service.container_port || 0 }});
        }}
      }}
      for (const field of catalogModule.config_schema || []) {{
        if (!(field.key in desiredModule.settings)) {{
          desiredModule.settings[field.key] = field.default ?? '';
        }}
      }}
    }}
    function inputForField(field) {{
      const value = desiredModule.settings?.[field.key] ?? field.default ?? '';
      const common = `data-setting="${{esc(field.key)}}"`;
      if (field.type === 'boolean') {{
        return `<label class="field"><span><input type="checkbox" ${{common}} ${{value === true ? 'checked' : ''}}> ${{esc(field.label || field.key)}}</span>${{field.help ? `<span class="help">${{esc(field.help)}}</span>` : ''}}</label>`;
      }}
      if (field.type === 'select') {{
        const options = (field.options || []).map((option) => `<option value="${{esc(option)}}" ${{String(value) === String(option) ? 'selected' : ''}}>${{esc(option)}}</option>`).join('');
        return `<label class="field">${{esc(field.label || field.key)}}<select ${{common}}>${{options}}</select>${{field.help ? `<span class="help">${{esc(field.help)}}</span>` : ''}}</label>`;
      }}
      if (field.type === 'textarea' || field.type === 'list') {{
        return `<label class="field wide">${{esc(field.label || field.key)}}<textarea ${{common}}>${{esc(Array.isArray(value) ? value.join('\\n') : value)}}</textarea>${{field.help ? `<span class="help">${{esc(field.help)}}</span>` : ''}}</label>`;
      }}
      const numberAttrs = field.type === 'integer' ? `type="number" step="1" ${{field.min !== undefined ? `min="${{esc(field.min)}}"` : ''}} ${{field.max !== undefined ? `max="${{esc(field.max)}}"` : ''}}` : 'type="text"';
      return `<label class="field">${{esc(field.label || field.key)}}<input ${{numberAttrs}} ${{common}} value="${{esc(value)}}">${{field.help ? `<span class="help">${{esc(field.help)}}</span>` : ''}}</label>`;
    }}
    function readSettingsFromInputs() {{
      for (const field of catalogModule.config_schema || []) {{
        const input = document.querySelector(`[data-setting="${{CSS.escape(field.key)}}"]`);
        if (!input) continue;
        if (field.type === 'boolean') {{
          desiredModule.settings[field.key] = input.checked;
        }} else if (field.type === 'integer') {{
          desiredModule.settings[field.key] = Number(input.value);
        }} else {{
          desiredModule.settings[field.key] = input.value;
        }}
      }}
    }}
    function render() {{
      ensureDesired();
      el('modulePurpose').textContent = catalogModule.purpose || '';
      el('moduleEnabled').checked = desiredModule.enabled !== false;
      el('services').innerHTML = `<table><thead><tr><th>Enabled</th><th>Service</th><th>Protocol</th><th>Host port</th><th>Default</th></tr></thead><tbody>${{(catalogModule.services || []).map((service) => {{
        const current = desiredModule.services.find((item) => item.id === service.id);
        return `<tr>
          <td><input type="checkbox" data-service-enabled="${{esc(service.id)}}" ${{current.enabled !== false ? 'checked' : ''}}></td>
          <td><code>${{esc(service.id)}}</code></td>
          <td>${{esc(service.protocol || 'tcp')}}</td>
          <td><input type="number" min="1" max="65535" data-service-port="${{esc(service.id)}}" value="${{esc(current.host_port || service.default_host_port || '')}}"></td>
          <td><code>${{esc(service.default_host_port || service.container_port || '')}}</code></td>
        </tr>`;
      }}).join('')}}</tbody></table>`;
      const fieldsByGroup = {{}};
      for (const field of catalogModule.config_schema || []) {{
        const group = field.group || 'General';
        fieldsByGroup[group] ||= [];
        fieldsByGroup[group].push(field);
      }}
      el('settings').innerHTML = Object.entries(fieldsByGroup).map(([group, fields]) => `
        <div class="field wide"><h3>${{esc(group)}}</h3></div>
        ${{fields.map(inputForField).join('')}}
      `).join('') || '<p class="muted">No settings schema for this module.</p>';
      document.querySelectorAll('[data-service-enabled]').forEach((input) => input.addEventListener('change', () => {{
        desiredModule.services.find((item) => item.id === input.dataset.serviceEnabled).enabled = input.checked;
      }}));
      document.querySelectorAll('[data-service-port]').forEach((input) => input.addEventListener('input', () => {{
        desiredModule.services.find((item) => item.id === input.dataset.servicePort).host_port = Number(input.value);
      }}));
      document.querySelectorAll('[data-setting]').forEach((input) => input.addEventListener('input', readSettingsFromInputs));
      document.querySelectorAll('[data-setting]').forEach((input) => input.addEventListener('change', readSettingsFromInputs));
    }}
    function renderEvents(events) {{
      el('events').innerHTML = events.map((event) => `<div>
        <strong>${{esc(event.event_type)}}</strong> <span class="muted">${{esc(event.service)}}:${{esc(event.dst_port)}} · from ${{esc(event.src_ip)}} · ${{age(event.received_at || event.timestamp)}}</span>
        <pre><code>${{esc(event.raw_sample || '')}}</code></pre>
      </div>`).join('') || '<p class="muted">No events yet.</p>';
    }}
    async function load() {{
      const [policyResponse, catalogResponse, eventResponse] = await Promise.all([
        fetch('/api/policy', {{ cache: 'no-store' }}),
        fetch('/api/modules', {{ cache: 'no-store' }}),
        fetch(`/api/events?suspicious=1&module=${{encodeURIComponent(moduleId)}}&limit=8`, {{ cache: 'no-store' }})
      ]);
      policy = (await policyResponse.json()).policy;
      const catalog = await catalogResponse.json();
      catalogModule = (catalog.modules || []).find((module) => module.id === moduleId);
      render();
      renderEvents((await eventResponse.json()).events || []);
    }}
    async function save() {{
      el('status').textContent = 'saving...';
      readSettingsFromInputs();
      desiredModule.enabled = el('moduleEnabled').checked;
      const payload = {{ enabled: desiredModule.enabled, services: desiredModule.services, settings: desiredModule.settings }};
      const response = await fetch(`/api/sensors/${{encodeURIComponent(sensorId)}}/modules/${{encodeURIComponent(moduleId)}}`, {{
        method: 'PATCH',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(payload)
      }});
      const result = await response.json();
      if (!response.ok) {{
        el('status').textContent = (result.errors || [result.error || 'save failed']).join('; ');
        el('status').className = 'bad';
        return;
      }}
      policy = result.policy;
      el('status').textContent = `saved. policy version ${{policy.version}}`;
      el('status').className = 'ok';
      render();
    }}
    el('save').addEventListener('click', save);
    el('reload').addEventListener('click', load);
    load();
    setInterval(async () => {{
      const response = await fetch(`/api/events?suspicious=1&module=${{encodeURIComponent(moduleId)}}&limit=8`, {{ cache: 'no-store' }});
      renderEvents((await response.json()).events || []);
    }}, 5000);
  </script>
</body>
</html>"""


class ControlPlaneHandler(BaseHTTPRequestHandler):
    catalog_path = DEFAULT_CATALOG
    policy_path = DEFAULT_POLICY
    store_path = DEFAULT_STORE

    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_html(self, payload: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_body(self) -> tuple[Any | None, str | None]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None, "invalid content length"
        try:
            return json.loads(self.rfile.read(length).decode("utf-8")), None
        except json.JSONDecodeError:
            return None, "invalid json"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        catalog = load_json(self.catalog_path)
        policy = load_json(self.policy_path)
        errors = policy_errors(policy, catalog)
        if errors and parsed.path not in ("", "/", "/health", "/api/modules"):
            self.send_json({"status": "invalid_policy", "errors": errors}, HTTPStatus.CONFLICT)
            return

        if parsed.path in ("", "/"):
            self.send_html(render_dashboard(policy))
            return
        if parsed.path.startswith("/honeypots/"):
            module_id = parsed.path.split("/", 2)[2]
            sensor_id = parse_qs(parsed.query).get("sensor_id", ["sensor1"])[0]
            page = render_honeypot_page(policy, catalog, sensor_id=sensor_id, module_id=module_id)
            if not page:
                self.send_json({"error": "honeypot module not found"}, HTTPStatus.NOT_FOUND)
                return
            self.send_html(page)
            return
        if parsed.path == "/health":
            self.send_json(
                {
                    "status": "ok" if not errors else "invalid_policy",
                    "site": policy.get("site", {}).get("name"),
                    "policy_version": int(policy.get("version", 1)),
                    "errors": errors,
                    "time": now_ts(),
                }
            )
            return
        if parsed.path == "/api/overview":
            events = read_events(self.store_path, limit=MAX_EVENT_LIMIT)
            self.send_json(overview_payload(policy, catalog, events))
            return
        if parsed.path == "/api/modules":
            self.send_json(catalog)
            return
        if parsed.path == "/api/policy":
            self.send_json({"policy": policy, "errors": errors})
            return
        if parsed.path == "/api/sensors":
            events = read_events(self.store_path, limit=MAX_EVENT_LIMIT)
            self.send_json(sensors_payload(policy, events))
            return
        if parsed.path.startswith("/api/sensors/") and parsed.path.endswith("/desired-state"):
            sensor_id = parsed.path.split("/")[3]
            state = desired_state(policy, catalog, sensor_id)
            if not state:
                self.send_json({"error": "sensor not found"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json(state)
            return
        if parsed.path == "/api/events":
            params = parse_qs(parsed.query)
            try:
                limit = int(params.get("limit", ["100"])[0])
            except ValueError:
                self.send_json({"error": "limit must be an integer"}, HTTPStatus.BAD_REQUEST)
                return
            events = read_events(self.store_path, MAX_EVENT_LIMIT)
            events = filter_events(events, params)
            limit = max(1, min(limit, MAX_EVENT_LIMIT))
            self.send_json({"events": events[-limit:]})
            return
        self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_PUT(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/policy":
            self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        payload, error = self.read_body()
        if error:
            self.send_json({"error": error}, HTTPStatus.BAD_REQUEST)
            return
        if not isinstance(payload, dict):
            self.send_json({"error": "payload must be an object"}, HTTPStatus.BAD_REQUEST)
            return
        policy = payload.get("policy", payload)
        catalog = load_json(self.catalog_path)
        errors = policy_errors(policy, catalog)
        if errors:
            self.send_json({"status": "invalid_policy", "errors": errors}, HTTPStatus.BAD_REQUEST)
            return
        policy = bump_policy_version(policy)
        write_json(self.policy_path, policy)
        self.send_json({"status": "saved", "policy": policy})

    def do_PATCH(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) not in {5, 7} or parts[:2] != ["api", "sensors"] or parts[3] != "modules":
            self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        sensor_id = parts[2]
        module_id = parts[4]
        service_id = parts[6] if len(parts) == 7 and parts[5] == "services" else None
        if len(parts) == 7 and parts[5] != "services":
            self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return

        payload, error = self.read_body()
        if error:
            self.send_json({"error": error}, HTTPStatus.BAD_REQUEST)
            return
        if not isinstance(payload, dict):
            self.send_json({"error": "payload must be an object"}, HTTPStatus.BAD_REQUEST)
            return

        catalog = load_json(self.catalog_path)
        policy = load_json(self.policy_path)
        sensor = find_sensor(policy, sensor_id)
        catalog_module = modules_by_id(catalog).get(module_id)
        if not sensor or not catalog_module:
            self.send_json({"error": "sensor or module not found"}, HTTPStatus.NOT_FOUND)
            return
        module = ensure_desired_module(sensor, catalog_module)

        if service_id:
            catalog_service = services_by_id(catalog_module).get(service_id)
            if not catalog_service:
                self.send_json({"error": "service not found"}, HTTPStatus.NOT_FOUND)
                return
            service = ensure_desired_service(module, catalog_service)
            if "enabled" in payload:
                service["enabled"] = bool(payload["enabled"])
            if "host_port" in payload:
                service["host_port"] = payload["host_port"]
        else:
            if "enabled" in payload:
                module["enabled"] = bool(payload["enabled"])
            if isinstance(payload.get("settings"), dict):
                settings = module.setdefault("settings", {})
                settings.update(payload["settings"])
            if isinstance(payload.get("services"), list):
                module["services"] = payload["services"]

        errors = policy_errors(policy, catalog)
        if errors:
            self.send_json({"status": "invalid_policy", "errors": errors}, HTTPStatus.BAD_REQUEST)
            return
        policy = bump_policy_version(policy)
        write_json(self.policy_path, policy)
        self.send_json({"status": "saved", "policy": policy})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in ("/api/events", "/api/enroll", "/api/sensors"):
            self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        payload, error = self.read_body()
        if error:
            self.send_json({"error": error}, HTTPStatus.BAD_REQUEST)
            return
        if not isinstance(payload, dict):
            self.send_json({"error": "payload must be an object"}, HTTPStatus.BAD_REQUEST)
            return
        catalog = load_json(self.catalog_path)
        policy = load_json(self.policy_path)
        if parsed.path == "/api/sensors":
            sensor_id = str(payload.get("id") or "").strip()
            if not sensor_id:
                self.send_json({"error": "sensor id is required"}, HTTPStatus.BAD_REQUEST)
                return
            if find_sensor(policy, sensor_id):
                self.send_json({"error": "sensor already exists"}, HTTPStatus.CONFLICT)
                return
            clone_from = str(payload.get("clone_from") or "sensor1")
            source = find_sensor(policy, clone_from) or (policy.get("sensors") or [None])[0]
            if not source:
                self.send_json({"error": "no source sensor to clone desired_state from"}, HTTPStatus.BAD_REQUEST)
                return
            sensor = {
                "id": sensor_id,
                "host": payload.get("host", ""),
                "architecture": payload.get("architecture", source.get("architecture", "")),
                "enrollment": payload.get("enrollment", {"method": "agent-polling"}),
                "desired_state": json.loads(json.dumps(payload.get("desired_state", source.get("desired_state", {})))),
            }
            policy.setdefault("sensors", []).append(sensor)
            errors = policy_errors(policy, catalog)
            if errors:
                self.send_json({"status": "invalid_policy", "errors": errors}, HTTPStatus.BAD_REQUEST)
                return
            policy = bump_policy_version(policy)
            write_json(self.policy_path, policy)
            self.send_json({"status": "saved", "sensor": sensor, "policy": policy}, HTTPStatus.CREATED)
            return
        errors = policy_errors(policy, catalog)
        if errors:
            self.send_json({"status": "invalid_policy", "errors": errors}, HTTPStatus.CONFLICT)
            return
        event_type = "sensor.enroll" if parsed.path == "/api/enroll" else payload.get("event_type", "sensor.event")
        event = {**payload, "event_type": event_type}
        write_event(self.store_path, event)
        response: dict[str, Any] = {"status": "accepted"}
        if parsed.path == "/api/enroll":
            sensor_id = str(payload.get("sensor_id") or payload.get("sensor") or "")
            state = desired_state(policy, catalog, sensor_id) if sensor_id else None
            response["registered"] = bool(state)
            if state:
                response["desired_state"] = state
            else:
                response["warning"] = "sensor is not present in policy"
        self.send_json(response, HTTPStatus.ACCEPTED)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"center: {self.address_string()} - {fmt % args}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run EDC control-plane MVP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ControlPlaneHandler.catalog_path = args.catalog
    ControlPlaneHandler.policy_path = args.policy
    ControlPlaneHandler.store_path = args.store
    server = ThreadingHTTPServer((args.host, args.port), ControlPlaneHandler)
    print(f"center: listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
