from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from .events import filter_events, read_events, write_event
from .installer import INSTALL_JOBS, install_sensor_job, job_log, new_job, public_job
from .overview import overview_payload, sensors_payload
from .paths import DEFAULT_CATALOG, DEFAULT_POLICY, DEFAULT_STORE, MAX_EVENT_LIMIT
from .policy import (
    bump_policy_version,
    desired_state,
    ensure_desired_module,
    ensure_desired_service,
    find_sensor,
    modules_by_id,
    policy_errors,
    services_by_id,
)
from .utils import load_json, now_ts, write_json
from .views import render_dashboard, render_honeypot_page

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
        if parsed.path == "/api/install-sensor":
            self.send_json({"jobs": [public_job(job) for job in INSTALL_JOBS.values()]})
            return
        if parsed.path.startswith("/api/install-sensor/"):
            job_id = parsed.path.split("/")[3]
            job = INSTALL_JOBS.get(job_id)
            if not job:
                self.send_json({"error": "installation job not found"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json({"job": public_job(job)})
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
        if parsed.path.startswith("/api/install-sensor/") and parsed.path.endswith("/cancel"):
            job_id = parsed.path.split("/")[3]
            job = INSTALL_JOBS.get(job_id)
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
            return
        if parsed.path not in ("/api/events", "/api/enroll", "/api/sensors", "/api/install-sensor"):
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
        if parsed.path == "/api/install-sensor":
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
            return
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
