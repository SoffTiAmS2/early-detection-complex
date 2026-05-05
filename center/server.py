#!/usr/bin/env python3
"""Minimal EDC control-plane MVP.

The server intentionally uses only the Python standard library. It exposes the
core HoneySens-like loop: sensors enroll, poll desired state and post events.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "catalog" / "honeypots.json"
DEFAULT_POLICY = ROOT / "config" / "site.example.json"
DEFAULT_STORE = ROOT / "var" / "center" / "events.jsonl"


def now_ts() -> float:
    return time.time()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_event(store: Path, event: dict[str, Any]) -> None:
    store.parent.mkdir(parents=True, exist_ok=True)
    event.setdefault("received_at", now_ts())
    with store.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def read_events(store: Path, limit: int) -> list[dict[str, Any]]:
    if not store.exists():
        return []
    events: list[dict[str, Any]] = []
    with store.open("r", encoding="utf-8") as fh:
        lines = deque(fh, maxlen=limit)
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"event_type": "parse_error", "raw": line})
    return events


def modules_by_id(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {module["id"]: module for module in catalog.get("modules", [])}


def services_by_id(module: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {service["id"]: service for service in module.get("services", [])}


def find_sensor(policy: dict[str, Any], sensor_id: str) -> dict[str, Any] | None:
    for sensor in policy.get("sensors", []):
        if sensor.get("id") == sensor_id:
            return sensor
    return None


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
                "services": planned_services,
            }
        )
    return {
        "sensor_id": sensor_id,
        "version": 1,
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
            },
        )
        item["events"] += 1
        item["last_seen"] = event.get("received_at") or event.get("timestamp")
        item["last_event_type"] = event.get("event_type") or event.get("type")
        if item["last_event_type"] == "sensor.status":
            item["status"] = event.get("status", item["status"])
            item["applied_version"] = event.get("applied_version", item["applied_version"])
            item["modules"] = event.get("modules", item["modules"])
    return sensors


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

        if parsed.path in ("", "/", "/health"):
            self.send_json({"status": "ok", "site": policy.get("site", {}).get("name"), "time": now_ts()})
            return
        if parsed.path == "/api/modules":
            self.send_json(catalog)
            return
        if parsed.path == "/api/sensors":
            events = read_events(self.store_path, limit=1000)
            summaries = sensor_summary(events)
            for sensor in policy.get("sensors", []):
                sensor_id = sensor.get("id")
                summaries.setdefault(
                    sensor_id,
                    {
                        "sensor_id": sensor_id,
                        "events": 0,
                        "last_seen": None,
                        "last_event_type": None,
                        "status": "never_seen",
                        "applied_version": None,
                        "modules": [],
                    },
                )
            self.send_json({"sensors": list(summaries.values())})
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
            self.send_json({"events": read_events(self.store_path, max(1, min(limit, 1000)))})
            return
        self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in ("/api/events", "/api/enroll"):
            self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        payload, error = self.read_body()
        if error:
            self.send_json({"error": error}, HTTPStatus.BAD_REQUEST)
            return
        if not isinstance(payload, dict):
            self.send_json({"error": "payload must be an object"}, HTTPStatus.BAD_REQUEST)
            return
        event_type = "sensor.enroll" if parsed.path == "/api/enroll" else payload.get("event_type", "sensor.event")
        event = {**payload, "event_type": event_type}
        write_event(self.store_path, event)
        self.send_json({"status": "accepted"}, HTTPStatus.ACCEPTED)

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
