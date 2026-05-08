from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from center.core.overview import overview_payload, sensors_payload
from center.core.paths import DEFAULT_CATALOG, DEFAULT_POLICY, DEFAULT_STORE, MAX_EVENT_LIMIT
from center.core.policy import (
    bump_policy_version,
    desired_state,
    ensure_desired_module,
    ensure_desired_service,
    find_sensor,
    modules_by_id,
    policy_errors,
    services_by_id,
)
from center.core.utils import load_json, now_ts, write_json
from center.persistence.events import filter_events, read_events, write_event
from center.services.installer import INSTALL_JOBS, install_sensor_job, job_log, new_job, public_job
from center.web.views import render_dashboard, render_honeypot_page


POLICY_SAFE_GET_PATHS = {"", "/", "/health", "/api/modules"}
JSON_POST_PATHS = {"/api/events", "/api/enroll", "/api/sensors", "/api/install-sensor"}


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
        catalog, policy, errors = self.load_catalog_and_policy()
        if errors and parsed.path not in POLICY_SAFE_GET_PATHS:
            self.send_json({"status": "invalid_policy", "errors": errors}, HTTPStatus.CONFLICT)
            return

        if parsed.path in ("", "/"):
            self.handle_dashboard(policy)
            return
        if parsed.path.startswith("/honeypots/"):
            self.handle_honeypot_page(parsed, policy, catalog)
            return
        if parsed.path == "/health":
            self.handle_health(policy, errors)
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
        if parsed.path == "/api/install-sensor":
            self.handle_install_jobs()
            return
        if parsed.path.startswith("/api/install-sensor/"):
            self.handle_install_job(parsed.path)
            return
        if parsed.path.startswith("/api/sensors/") and parsed.path.endswith("/desired-state"):
            self.handle_desired_state(parsed.path, policy, catalog)
            return
        if parsed.path == "/api/events":
            self.handle_events_query(parsed.query)
            return
        self.send_not_found()

    def handle_dashboard(self, policy: dict[str, Any]) -> None:
        self.send_html(render_dashboard(policy))

    def handle_honeypot_page(self, parsed: Any, policy: dict[str, Any], catalog: dict[str, Any]) -> None:
        module_id = parsed.path.split("/", 2)[2]
        sensor_id = parse_qs(parsed.query).get("sensor_id", ["sensor1"])[0]
        page = render_honeypot_page(policy, catalog, sensor_id=sensor_id, module_id=module_id)
        if not page:
            self.send_json({"error": "honeypot module not found"}, HTTPStatus.NOT_FOUND)
            return
        self.send_html(page)

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

    def handle_install_jobs(self) -> None:
        self.send_json({"jobs": [public_job(job) for job in INSTALL_JOBS.values()]})

    def handle_install_job(self, path: str) -> None:
        parts = [part for part in path.split("/") if part]
        if len(parts) != 3:
            self.send_json({"error": "installation job not found"}, HTTPStatus.NOT_FOUND)
            return
        job = INSTALL_JOBS.get(parts[2])
        if not job:
            self.send_json({"error": "installation job not found"}, HTTPStatus.NOT_FOUND)
            return
        self.send_json({"job": public_job(job)})

    def handle_desired_state(self, path: str, policy: dict[str, Any], catalog: dict[str, Any]) -> None:
        sensor_id = path.split("/")[3]
        state = desired_state(policy, catalog, sensor_id)
        if not state:
            self.send_json({"error": "sensor not found"}, HTTPStatus.NOT_FOUND)
            return
        self.send_json(state)

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

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/install-sensor/") and parsed.path.endswith("/cancel"):
            self.handle_install_cancel(parsed.path)
            return
        if parsed.path not in JSON_POST_PATHS:
            self.send_not_found()
            return
        payload, ok = self.read_json_object()
        if not ok or payload is None:
            return

        catalog = load_json(self.catalog_path)
        policy = load_json(self.policy_path)
        if parsed.path == "/api/install-sensor":
            self.handle_install_sensor(payload)
            return
        if parsed.path == "/api/sensors":
            self.handle_create_sensor(payload, policy, catalog)
            return
        self.handle_sensor_event(parsed.path, payload, policy, catalog)

    def handle_install_cancel(self, path: str) -> None:
        parts = [part for part in path.split("/") if part]
        if len(parts) != 4:
            self.send_json({"error": "installation job not found"}, HTTPStatus.NOT_FOUND)
            return
        job = INSTALL_JOBS.get(parts[2])
        if not job:
            self.send_json({"error": "installation job not found"}, HTTPStatus.NOT_FOUND)
            return
        job["cancel_requested"] = True
        process = job.get("process")
        if process and process.poll() is None:
            process.terminate()
        job["status"] = "cancelled"
        job_log(job, "Отмена запрошена пользователем", step="Отменено")
        self.send_json({"job": public_job(job)})

    def handle_install_sensor(self, payload: dict[str, Any]) -> None:
        sensor_id = str(payload.get("sensor_id") or "").strip()
        host = str(payload.get("host") or "").strip()
        if not sensor_id or not host:
            self.send_json({"error": "Укажите имя сенсора и IP адрес"}, HTTPStatus.BAD_REQUEST)
            return
        job = new_job(sensor_id, host)
        thread = threading.Thread(
            target=install_sensor_job,
            args=(job, payload, self.policy_path, self.catalog_path, dict(self.headers)),
            daemon=True,
        )
        thread.start()
        self.send_json({"job": public_job(job)}, HTTPStatus.ACCEPTED)

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

    def handle_sensor_event(
        self,
        path: str,
        payload: dict[str, Any],
        policy: dict[str, Any],
        catalog: dict[str, Any],
    ) -> None:
        errors = policy_errors(policy, catalog)
        if errors:
            self.send_json({"status": "invalid_policy", "errors": errors}, HTTPStatus.CONFLICT)
            return
        event_type = "sensor.enroll" if path == "/api/enroll" else payload.get("event_type", "sensor.event")
        event = {**payload, "event_type": event_type}
        write_event(self.store_path, event)
        response: dict[str, Any] = {"status": "accepted"}
        if path == "/api/enroll":
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
