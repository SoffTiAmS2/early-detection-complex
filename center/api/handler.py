from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from center.core.auth import auth_required_response, is_admin_route, is_authorized
from center.core.metrics import prometheus_metrics
from center.core.overview import overview_payload, sensors_payload
from center.core.paths import DEFAULT_CATALOG, DEFAULT_POLICY, DEFAULT_STORE, MAX_EVENT_LIMIT
from center.core.policy import (
    bump_policy_version,
    ensure_desired_module,
    ensure_desired_service,
    find_sensor,
    modules_by_id,
    policy_errors,
    remove_sensor,
    services_by_id,
)
from center.core.sensor_sync import sensor_sync
from center.core.utils import load_json, now_ts, write_json
from center.persistence.events import filter_events, purge_sensor_events, read_events, write_event
from center.web.views import render_admin_page


POLICY_SAFE_GET_PATHS = {"", "/", "/settings", "/health", "/metrics", "/api/modules"}
JSON_POST_PATHS = {"/api/events", "/api/sensors"}


class ControlPlaneHandler(BaseHTTPRequestHandler):
    catalog_path = DEFAULT_CATALOG
    policy_path = DEFAULT_POLICY
    store_path = DEFAULT_STORE

    # Small response helpers keep route methods focused on project logic.
    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_text(self, payload: str, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_html(self, payload: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_text(payload, "text/html; charset=utf-8", status)

    def require_admin_auth(self, method: str, path: str) -> bool:
        if not is_admin_route(method, path) or is_authorized(self.headers):
            return True
        payload, status = auth_required_response()
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("WWW-Authenticate", 'Basic realm="EDC center"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        return False

    def read_body(self) -> tuple[Any | None, str | None]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None, "invalid content length"
        try:
            return json.loads(self.rfile.read(length).decode("utf-8")), None
        except json.JSONDecodeError:
            return None, "invalid json"

    def read_json_object(self) -> tuple[dict[str, Any] | None, bool]:
        payload, error = self.read_body()
        if error:
            self.send_json({"error": error}, HTTPStatus.BAD_REQUEST)
            return None, False
        if not isinstance(payload, dict):
            self.send_json({"error": "payload must be an object"}, HTTPStatus.BAD_REQUEST)
            return None, False
        return payload, True

    def load_catalog_and_policy(self) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        catalog = load_json(self.catalog_path)
        policy = load_json(self.policy_path)
        return catalog, policy, policy_errors(policy, catalog)

    def save_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        updated = bump_policy_version(policy)
        write_json(self.policy_path, updated)
        return updated

    def send_not_found(self) -> None:
        self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self.require_admin_auth("GET", parsed.path):
            return
        catalog, policy, errors = self.load_catalog_and_policy()
        if errors and parsed.path not in POLICY_SAFE_GET_PATHS:
            self.send_json({"status": "invalid_policy", "errors": errors}, HTTPStatus.CONFLICT)
            return

        if parsed.path in ("", "/", "/settings"):
            self.send_html(render_admin_page(policy))
            return
        if parsed.path == "/health":
            self.handle_health(policy, errors)
            return
        if parsed.path == "/metrics":
            self.handle_metrics(policy)
            return
        if parsed.path == "/api/overview":
            self.handle_overview(policy, catalog)
            return
        if parsed.path == "/api/modules":
            self.send_json(catalog)
            return
        if parsed.path == "/api/policy":
            self.send_json({"policy": policy, "errors": errors})
            return
        if parsed.path == "/api/sensors":
            self.handle_sensors(policy)
            return
        if parsed.path == "/api/events":
            self.handle_events_query(parsed.query)
            return
        self.send_not_found()

    def handle_health(self, policy: dict[str, Any], errors: list[str]) -> None:
        self.send_json(
            {
                "status": "ok" if not errors else "invalid_policy",
                "site": policy.get("site", {}).get("name"),
                "policy_version": int(policy.get("version", 1)),
                "errors": errors,
                "time": now_ts(),
            }
        )

    def handle_overview(self, policy: dict[str, Any], catalog: dict[str, Any]) -> None:
        events = read_events(self.store_path, limit=MAX_EVENT_LIMIT)
        self.send_json(overview_payload(policy, catalog, events))

    def handle_sensors(self, policy: dict[str, Any]) -> None:
        events = read_events(self.store_path, limit=MAX_EVENT_LIMIT)
        self.send_json(sensors_payload(policy, events))

    def handle_metrics(self, policy: dict[str, Any]) -> None:
        events = read_events(self.store_path, limit=MAX_EVENT_LIMIT)
        self.send_text(prometheus_metrics(policy, events), "text/plain; version=0.0.4; charset=utf-8")

    def handle_events_query(self, query: str) -> None:
        params = parse_qs(query)
        try:
            limit = int(params.get("limit", ["100"])[0])
        except ValueError:
            self.send_json({"error": "limit must be an integer"}, HTTPStatus.BAD_REQUEST)
            return
        events = read_events(self.store_path, MAX_EVENT_LIMIT)
        events = filter_events(events, params)
        limit = max(1, min(limit, MAX_EVENT_LIMIT))
        self.send_json({"events": events[-limit:]})

    def do_PUT(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self.require_admin_auth("PUT", parsed.path):
            return
        if parsed.path != "/api/policy":
            self.send_not_found()
            return
        payload, ok = self.read_json_object()
        if not ok or payload is None:
            return

        policy = payload.get("policy", payload)
        catalog = load_json(self.catalog_path)
        errors = policy_errors(policy, catalog)
        if errors:
            self.send_json({"status": "invalid_policy", "errors": errors}, HTTPStatus.BAD_REQUEST)
            return
        policy = self.save_policy(policy)
        self.send_json({"status": "saved", "policy": policy})

    def do_PATCH(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self.require_admin_auth("PATCH", parsed.path):
            return
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) not in {5, 7} or parts[:2] != ["api", "sensors"] or parts[3] != "modules":
            self.send_not_found()
            return
        sensor_id = parts[2]
        module_id = parts[4]
        service_id = parts[6] if len(parts) == 7 and parts[5] == "services" else None
        if len(parts) == 7 and parts[5] != "services":
            self.send_not_found()
            return

        payload, ok = self.read_json_object()
        if not ok or payload is None:
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
        policy = self.save_policy(policy)
        self.send_json({"status": "saved", "policy": policy})

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self.require_admin_auth("DELETE", parsed.path):
            return
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 3 or parts[:2] != ["api", "sensors"]:
            self.send_not_found()
            return
        sensor_id = unquote(parts[2])
        catalog = load_json(self.catalog_path)
        policy = load_json(self.policy_path)
        if not find_sensor(policy, sensor_id):
            self.send_json({"error": "sensor not found"}, HTTPStatus.NOT_FOUND)
            return
        remove_sensor(policy, sensor_id)
        errors = policy_errors(policy, catalog)
        if errors:
            self.send_json({"status": "invalid_policy", "errors": errors}, HTTPStatus.BAD_REQUEST)
            return
        policy = self.save_policy(policy)
        purge = parse_qs(parsed.query).get("purge_events", ["0"])[0] in {"1", "true", "yes"}
        purged_events = purge_sensor_events(self.store_path, sensor_id) if purge else 0
        self.send_json({"status": "deleted", "sensor_id": sensor_id, "purged_events": purged_events, "policy": policy})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self.require_admin_auth("POST", parsed.path):
            return
        is_sensor_sync = self.is_sensor_sync_path(parsed.path)
        if parsed.path not in JSON_POST_PATHS and not is_sensor_sync:
            self.send_not_found()
            return
        payload, ok = self.read_json_object()
        if not ok or payload is None:
            return

        catalog = load_json(self.catalog_path)
        policy = load_json(self.policy_path)
        if parsed.path == "/api/sensors":
            self.handle_create_sensor(payload, policy, catalog)
            return
        if is_sensor_sync:
            self.handle_sensor_sync(parsed.path, payload, policy, catalog)
            return
        self.handle_sensor_event(payload, policy, catalog)

    def is_sensor_sync_path(self, path: str) -> bool:
        parts = [part for part in path.split("/") if part]
        return len(parts) == 4 and parts[:2] == ["api", "sensors"] and parts[3] == "sync"

    def handle_create_sensor(self, payload: dict[str, Any], policy: dict[str, Any], catalog: dict[str, Any]) -> None:
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
        policy = self.save_policy(policy)
        self.send_json({"status": "saved", "sensor": sensor, "policy": policy}, HTTPStatus.CREATED)

    def handle_sensor_sync(
        self,
        path: str,
        payload: dict[str, Any],
        policy: dict[str, Any],
        catalog: dict[str, Any],
    ) -> None:
        parts = [part for part in path.split("/") if part]
        sensor_id = unquote(parts[2])
        errors = policy_errors(policy, catalog)
        if errors:
            self.send_json({"status": "invalid_policy", "errors": errors}, HTTPStatus.CONFLICT)
            return
        event, response = sensor_sync(policy, catalog, sensor_id, payload)
        write_event(self.store_path, event)
        self.send_json(response, HTTPStatus.ACCEPTED)

    def handle_sensor_event(
        self,
        payload: dict[str, Any],
        policy: dict[str, Any],
        catalog: dict[str, Any],
    ) -> None:
        errors = policy_errors(policy, catalog)
        if errors:
            self.send_json({"status": "invalid_policy", "errors": errors}, HTTPStatus.CONFLICT)
            return
        event = {**payload, "event_type": payload.get("event_type", "sensor.event")}
        write_event(self.store_path, event)
        self.send_json({"status": "accepted"}, HTTPStatus.ACCEPTED)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"center: {self.address_string()} - {fmt % args}")
