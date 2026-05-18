from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from center.core.bootstrap import latest_bootstrap_job, list_bootstrap_jobs, start_sensor_bootstrap
from center.core.auth import auth_required_response, is_admin_route, is_authorized
from center.core.overview import overview_payload, sensors_payload
from center.core.paths import DEFAULT_CATALOG, DEFAULT_DEVICE_PROFILES, DEFAULT_POLICY, DEFAULT_STORE, MAX_EVENT_LIMIT
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
from center.core.profiles import apply_profile, available_profiles
from center.core.sensor_sync import sensor_sync
from center.core.utils import load_json, now_ts, write_json
from center.persistence.events import database_stats, filter_events, purge_all_events, purge_sensor_events, read_events, write_event
from center.persistence.honeypot_logs import (
    honeypot_database_stats,
    read_honeypot_events,
    read_raw_honeypot_logs,
    write_honeypot_batch,
    write_honeypot_observation,
)
from center.persistence.sensor_states import read_sensor_states, should_persist_status_event, write_sensor_state
from center.web.views import render_admin_page, render_database_page, render_mask_page, render_profiles_page


POLICY_SAFE_GET_PATHS = {
    "",
    "/",
    "/settings",
    "/db",
    "/mask",
    "/profiles",
    "/health",
    "/api/modules",
    "/api/profiles",
    "/api/device-mask-profiles",
    "/api/db/stats",
}
JSON_POST_PATHS = {
    "/api/events",
    "/api/sensors",
    "/api/sensors/bootstrap",
    "/api/mask",
    "/api/logs/batch",
    "/api/logs/events",
    "/api/logs/raw",
}


class ControlPlaneHandler(BaseHTTPRequestHandler):
    catalog_path = DEFAULT_CATALOG
    profile_path = DEFAULT_DEVICE_PROFILES
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
        if parsed.path == "/db":
            self.send_html(render_database_page(policy))
            return
        if parsed.path == "/mask":
            self.send_html(render_mask_page(policy))
            return
        if parsed.path == "/profiles":
            self.send_html(render_profiles_page(policy))
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
        if parsed.path in {"/api/profiles", "/api/device-mask-profiles"}:
            profile_catalog = load_json(self.profile_path)
            self.send_json({"profiles": list(available_profiles(policy, catalog, profile_catalog).values())})
            return
        if parsed.path == "/api/policy":
            self.send_json({"policy": policy, "errors": errors})
            return
        if parsed.path == "/api/sensors":
            self.handle_sensors(policy)
            return
        if parsed.path == "/api/sensor-installs":
            self.send_json({"jobs": list_bootstrap_jobs()})
            return
        if parsed.path == "/api/events":
            self.handle_events_query(parsed.query)
            return
        if parsed.path == "/api/honeypot-events":
            self.handle_honeypot_events_query(parsed.query)
            return
        if parsed.path == "/api/logs/raw":
            self.handle_raw_logs_query(parsed.query)
            return
        if parsed.path == "/api/db/stats":
            self.send_json({**database_stats(self.store_path), **honeypot_database_stats(self.store_path)})
            return
        if parsed.path == "/api/mask":
            self.send_json({"policy": policy, "errors": errors})
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
        self.send_json(overview_payload(policy, catalog, events, read_sensor_states(self.store_path)))

    def handle_sensors(self, policy: dict[str, Any]) -> None:
        events = read_events(self.store_path, limit=MAX_EVENT_LIMIT)
        payload = sensors_payload(policy, events, read_sensor_states(self.store_path))
        for sensor in payload.get("sensors", []):
            job = latest_bootstrap_job(str(sensor.get("sensor_id") or ""))
            if not job or job.get("status") == "completed" and sensor.get("health") == "online":
                continue
            if job.get("status") in {"queued", "running", "failed", "completed"}:
                sensor["provisioning"] = {
                    **(sensor.get("provisioning") if isinstance(sensor.get("provisioning"), dict) else {}),
                    "status": "installing" if job.get("status") in {"queued", "running"} else job.get("status"),
                    "stage": job.get("stage"),
                    "progress": job.get("progress"),
                    "message": job.get("message"),
                    "job_id": job.get("id"),
                }
        self.send_json(payload)

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

    def handle_honeypot_events_query(self, query: str) -> None:
        params = parse_qs(query)
        try:
            limit = int(params.get("limit", ["100"])[0])
        except ValueError:
            self.send_json({"error": "limit must be an integer"}, HTTPStatus.BAD_REQUEST)
            return
        self.send_json({"events": read_honeypot_events(self.store_path, limit, self.honeypot_filters(params))})

    def handle_raw_logs_query(self, query: str) -> None:
        params = parse_qs(query)
        try:
            limit = int(params.get("limit", ["100"])[0])
        except ValueError:
            self.send_json({"error": "limit must be an integer"}, HTTPStatus.BAD_REQUEST)
            return
        self.send_json({"logs": read_raw_honeypot_logs(self.store_path, limit, self.honeypot_filters(params))})

    def honeypot_filters(self, params: dict[str, list[str]]) -> dict[str, str]:
        keys = {
            "sensor_id",
            "profile",
            "device_type",
            "honeypot",
            "module",
            "service",
            "event_type",
            "severity",
            "src_ip",
            "dst_port",
            "source_name",
            "container_name",
            "q",
        }
        return {key: params.get(key, [""])[0].strip() for key in keys if params.get(key, [""])[0].strip()}

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
        if parsed.path == "/api/site":
            payload, ok = self.read_json_object()
            if not ok or payload is None:
                return
            policy = load_json(self.policy_path)
            catalog = load_json(self.catalog_path)
            site = policy.setdefault("site", {})
            if "name" in payload:
                site["name"] = str(payload.get("name") or site.get("name") or "")
            if "central_url" in payload:
                site["central_url"] = str(payload.get("central_url") or "")
            if "management_network" in payload:
                site["management_network"] = str(payload.get("management_network") or "")
            if isinstance(payload.get("observability"), dict):
                obs = site.setdefault("observability", {})
                obs.update(payload["observability"])
            errors = policy_errors(policy, catalog)
            if errors:
                self.send_json({"status": "invalid_policy", "errors": errors}, HTTPStatus.BAD_REQUEST)
                return
            policy = self.save_policy(policy)
            self.send_json({"status": "saved", "site": policy.get("site", {}), "policy": policy})
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
        purge = parse_qs(parsed.query).get("purge_events", ["1"])[0] in {"1", "true", "yes"}
        purged_events = purge_sensor_events(self.store_path, sensor_id) if purge else 0
        self.send_json({"status": "deleted", "sensor_id": sensor_id, "purged_events": purged_events, "policy": policy})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self.require_admin_auth("POST", parsed.path):
            return
        is_sensor_sync = self.is_sensor_sync_path(parsed.path)
        if parsed.path not in JSON_POST_PATHS and not is_sensor_sync:
            if not self.is_apply_profile_path(parsed.path):
                if parsed.path != "/api/db/purge":
                    self.send_not_found()
                    return
        payload, ok = self.read_json_object()
        if not ok or payload is None:
            return

        catalog = load_json(self.catalog_path)
        policy = load_json(self.policy_path)
        if parsed.path == "/api/db/purge":
            deleted = purge_all_events(self.store_path)
            self.send_json({"status": "purged", "deleted_events": deleted, "stats": database_stats(self.store_path)})
            return
        if parsed.path == "/api/mask":
            self.handle_mask_update(payload, policy, catalog)
            return
        if parsed.path in {"/api/logs/batch", "/api/logs/events", "/api/logs/raw"}:
            self.handle_logs_ingest(payload)
            return
        if self.is_apply_profile_path(parsed.path):
            self.handle_apply_profile(parsed.path, payload, policy, catalog)
            return
        if parsed.path == "/api/sensors":
            self.handle_create_sensor(payload, policy, catalog)
            return
        if parsed.path == "/api/sensors/bootstrap":
            self.handle_bootstrap_sensor(payload, policy, catalog)
            return
        if is_sensor_sync:
            self.handle_sensor_sync(parsed.path, payload, policy, catalog)
            return
        self.handle_sensor_event(payload, policy, catalog)

    def handle_logs_ingest(self, payload: dict[str, Any]) -> None:
        events_payload = payload.get("events") or payload.get("logs") or payload.get("items")
        if events_payload is None:
            events_payload = [payload]
        if not isinstance(events_payload, list) or not all(isinstance(item, dict) for item in events_payload):
            self.send_json({"error": "events/logs/items must be a list of objects"}, HTTPStatus.BAD_REQUEST)
            return
        result = write_honeypot_batch(self.store_path, events_payload)
        self.send_json({"status": "accepted", **result}, HTTPStatus.ACCEPTED)

    def is_sensor_sync_path(self, path: str) -> bool:
        parts = [part for part in path.split("/") if part]
        return len(parts) == 4 and parts[:2] == ["api", "sensors"] and parts[3] == "sync"

    def is_apply_profile_path(self, path: str) -> bool:
        parts = [part for part in path.split("/") if part]
        return len(parts) == 4 and parts[:2] == ["api", "sensors"] and parts[3] == "apply-profile"

    def handle_create_sensor(self, payload: dict[str, Any], policy: dict[str, Any], catalog: dict[str, Any]) -> None:
        sensor_id = str(payload.get("id") or "").strip()
        if not sensor_id:
            self.send_json({"error": "sensor id is required"}, HTTPStatus.BAD_REQUEST)
            return
        if find_sensor(policy, sensor_id):
            self.send_json({"error": "sensor already exists"}, HTTPStatus.CONFLICT)
            return
        profile_id = str(payload.get("profile_id") or "").strip()
        clone_from = str(payload.get("clone_from") or "").strip()
        source = find_sensor(policy, clone_from) if clone_from else None
        source = source or (policy.get("sensors") or [None])[0]
        if not source and not profile_id:
            self.send_json({"error": "no source sensor to clone desired_state from"}, HTTPStatus.BAD_REQUEST)
            return
        sensor = {
            "id": sensor_id,
            "host": payload.get("host", ""),
            "architecture": payload.get("architecture", source.get("architecture", "") if source else ""),
            "enrollment": payload.get("enrollment", {"method": "agent-polling"}),
            "desired_state": json.loads(json.dumps(payload.get("desired_state", source.get("desired_state", {}) if source else {}))),
        }
        if profile_id:
            ok_apply, error = apply_profile(policy, catalog, sensor, profile_id, load_json(self.profile_path))
            if not ok_apply:
                self.send_json({"error": error}, HTTPStatus.BAD_REQUEST)
                return
        created_at = now_ts()
        operation = {
            "id": f"sensor-create:{sensor_id}:{int(created_at)}",
            "type": "sensor-create",
            "sensor_id": sensor_id,
            "status": "waiting_agent",
            "stage": "policy_saved",
            "progress": 45,
            "message": "Сенсор создан в политике. Ожидается первый sync от sensor-agent.",
            "created_at": created_at,
            "updated_at": created_at,
            "next_action": "Запусти sensor-agent на узле сенсора или через compose.sensor.yml.",
        }
        sensor["provisioning"] = operation
        policy.setdefault("sensors", []).append(sensor)
        errors = policy_errors(policy, catalog)
        if errors:
            self.send_json({"status": "invalid_policy", "errors": errors}, HTTPStatus.BAD_REQUEST)
            return
        policy = self.save_policy(policy)
        self.send_json({"status": "processing", "sensor": sensor, "operation": operation, "policy": policy}, HTTPStatus.CREATED)

    def handle_bootstrap_sensor(self, payload: dict[str, Any], policy: dict[str, Any], catalog: dict[str, Any]) -> None:
        sensor_id = str(payload.get("id") or payload.get("sensor_id") or "").strip()
        host = str(payload.get("host") or "").strip()
        ssh_user = str(payload.get("ssh_user") or "").strip()
        ssh_password = str(payload.get("ssh_password") or "").strip()
        if not sensor_id or not host or not ssh_user or not ssh_password:
            self.send_json({"error": "sensor id, host, ssh_user and ssh_password are required"}, HTTPStatus.BAD_REQUEST)
            return

        profile_id = str(payload.get("profile_id") or "").strip()
        sensor = find_sensor(policy, sensor_id)
        if sensor is None:
            source_id = str(payload.get("clone_from") or "").strip()
            source = find_sensor(policy, source_id) if source_id else None
            source = source or (policy.get("sensors") or [None])[0]
            if not source and not profile_id:
                self.send_json({"error": "profile_id is required for the first sensor"}, HTTPStatus.BAD_REQUEST)
                return
            sensor = {
                "id": sensor_id,
                "host": host,
                "architecture": str(payload.get("architecture") or (source.get("architecture", "") if source else "")),
                "enrollment": {"method": "ssh-bootstrap", "ssh_user": ssh_user, "ssh_port": int(payload.get("ssh_port") or 22)},
                "desired_state": json.loads(json.dumps(payload.get("desired_state", source.get("desired_state", {}) if source else {}))),
            }
            policy.setdefault("sensors", []).append(sensor)
        else:
            sensor["host"] = host
            sensor["enrollment"] = {"method": "ssh-bootstrap", "ssh_user": ssh_user, "ssh_port": int(payload.get("ssh_port") or 22)}

        if profile_id:
            ok_apply, error = apply_profile(policy, catalog, sensor, profile_id, load_json(self.profile_path))
            if not ok_apply:
                self.send_json({"error": error}, HTTPStatus.BAD_REQUEST)
                return

        central_url = str(payload.get("center_url") or policy.get("site", {}).get("central_url") or "").strip()
        if not central_url:
            self.send_json({"error": "center_url is required in site settings or bootstrap payload"}, HTTPStatus.BAD_REQUEST)
            return

        job = start_sensor_bootstrap(
            {
                "sensor_id": sensor_id,
                "host": host,
                "ssh_user": ssh_user,
                "ssh_password": ssh_password,
                "ssh_port": int(payload.get("ssh_port") or 22),
                "remote_dir": str(payload.get("remote_dir") or "~/early-detection-complex"),
                "center_url": central_url,
                "image_policy": str(payload.get("image_policy") or "prebuilt_only"),
                "log_receiver_url": str(payload.get("log_receiver_url") or ""),
            }
        )
        operation = {
            "id": f"sensor-bootstrap:{sensor_id}:{job['id']}",
            "type": "sensor-bootstrap",
            "job_id": job["id"],
            "sensor_id": sensor_id,
            "status": "installing",
            "stage": "ssh_bootstrap",
            "progress": 10,
            "message": "Центр устанавливает sensor-agent по SSH.",
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
            "next_action": "Открой статус установки в этом же разделе. На сенсор вручную заходить не требуется.",
        }
        sensor["provisioning"] = operation
        errors = policy_errors(policy, catalog)
        if errors:
            self.send_json({"status": "invalid_policy", "errors": errors}, HTTPStatus.BAD_REQUEST)
            return
        policy = self.save_policy(policy)
        self.send_json({"status": "installing", "operation": operation, "job": job, "sensor": sensor, "policy": policy}, HTTPStatus.ACCEPTED)

    def handle_apply_profile(
        self,
        path: str,
        payload: dict[str, Any],
        policy: dict[str, Any],
        catalog: dict[str, Any],
    ) -> None:
        parts = [part for part in path.split("/") if part]
        sensor_id = unquote(parts[2])
        sensor = find_sensor(policy, sensor_id)
        if not sensor:
            self.send_json({"error": "sensor not found"}, HTTPStatus.NOT_FOUND)
            return
        profile_id = str(payload.get("profile_id") or "").strip()
        if not profile_id:
            self.send_json({"error": "profile_id is required"}, HTTPStatus.BAD_REQUEST)
            return
        ok_apply, error = apply_profile(policy, catalog, sensor, profile_id, load_json(self.profile_path))
        if not ok_apply:
            self.send_json({"error": error}, HTTPStatus.BAD_REQUEST)
            return
        errors = policy_errors(policy, catalog)
        if errors:
            self.send_json({"status": "invalid_policy", "errors": errors}, HTTPStatus.BAD_REQUEST)
            return
        policy = self.save_policy(policy)
        self.send_json({"status": "saved", "sensor": sensor, "policy": policy})

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
        event["received_at"] = now_ts()
        write_sensor_state(self.store_path, event)
        if should_persist_status_event(event):
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
        normalized = write_honeypot_observation(self.store_path, event)
        self.send_json({"status": "accepted", "normalized": bool(normalized)}, HTTPStatus.ACCEPTED)

    def handle_mask_update(self, payload: dict[str, Any], policy: dict[str, Any], catalog: dict[str, Any]) -> None:
        sensor_id = str(payload.get("sensor_id") or "").strip()
        if not sensor_id:
            self.send_json({"error": "sensor_id is required"}, HTTPStatus.BAD_REQUEST)
            return
        sensor = find_sensor(policy, sensor_id)
        if not sensor:
            self.send_json({"error": "sensor not found"}, HTTPStatus.NOT_FOUND)
            return
        desired = sensor.setdefault("desired_state", {})
        modules = desired.setdefault("modules", [])
        module_index = {str(m.get("id")): m for m in modules if isinstance(m, dict)}

        def copy_json(value: Any) -> Any:
            return json.loads(json.dumps(value, ensure_ascii=False))

        def module_settings(mid: str, *, create: bool = False) -> dict[str, Any] | None:
            module = module_index.get(mid)
            if not module:
                if not create:
                    return None
                module = {"id": mid, "enabled": True, "services": [], "settings": {}}
                modules.append(module)
                module_index[mid] = module
            settings = module.setdefault("settings", {})
            if not isinstance(settings, dict):
                settings = {}
                module["settings"] = settings
            return settings

        def string_map(source: Any, keys: tuple[str, ...]) -> dict[str, str]:
            if not isinstance(source, dict):
                return {}
            result: dict[str, str] = {}
            for key in keys:
                if key in source:
                    result[key] = str(source.get(key) or "").strip()
            return result

        def merge_string_dict(target_key: str, source: Any, keys: tuple[str, ...]) -> dict[str, Any]:
            current = desired.get(target_key)
            if not isinstance(current, dict):
                current = {}
                desired[target_key] = current
            current.update(string_map(source, keys))
            return current

        def merge_flexible_dict(target_key: str, source: Any) -> dict[str, Any]:
            current = desired.get(target_key)
            if not isinstance(current, dict):
                current = {}
                desired[target_key] = current
            if not isinstance(source, dict):
                return current
            for key, value in source.items():
                if isinstance(value, list):
                    current[str(key)] = [str(item).strip() for item in value if str(item).strip()]
                elif isinstance(value, dict):
                    current[str(key)] = copy_json(value)
                else:
                    current[str(key)] = str(value or "").strip()
            return current

        cowrie = payload.get("cowrie") if isinstance(payload.get("cowrie"), dict) else {}
        honeypy = payload.get("honeypy") if isinstance(payload.get("honeypy"), dict) else {}
        mailoney = payload.get("mailoney") if isinstance(payload.get("mailoney"), dict) else {}
        glutton = payload.get("glutton") if isinstance(payload.get("glutton"), dict) else {}
        raw_overrides = payload.get("raw_overrides") if isinstance(payload.get("raw_overrides"), dict) else {}

        legend = merge_string_dict(
            "legend",
            payload.get("legend"),
            ("summary", "hostname", "vendor", "location", "os_family"),
        )
        desired["persona"] = {**(desired.get("persona") if isinstance(desired.get("persona"), dict) else {}), **copy_json(legend)}
        banners = merge_flexible_dict("banners", payload.get("banners"))
        fingerprints = merge_flexible_dict("service_fingerprints", payload.get("service_fingerprints"))
        resources = merge_string_dict("resource_limits", payload.get("resource_limits"), ("memory_limit", "cpu_limit"))

        hostname = str(banners.get("hostname") or legend.get("hostname") or "").strip()
        if hostname:
            legend["hostname"] = hostname
            desired["persona"]["hostname"] = hostname
            banners["hostname"] = hostname

        desired_modules = {str(mid) for mid in desired.get("honeypots", []) if isinstance(mid, str)}
        if not desired_modules:
            desired_modules = set(module_index)

        for mid in desired_modules:
            settings = module_settings(mid, create=mid in module_index)
            if settings is None:
                continue
            if resources:
                settings["resource_limits"] = copy_json(resources)
            if banners:
                settings["banners"] = copy_json(banners)
            if fingerprints:
                settings["service_fingerprints"] = copy_json(fingerprints)

            if mid == "cowrie":
                if hostname:
                    settings["hostname"] = hostname
                if banners.get("ssh_banner"):
                    settings["ssh_version"] = str(banners.get("ssh_banner"))
                if banners.get("telnet_banner"):
                    settings["telnet_banner"] = str(banners.get("telnet_banner"))
            elif mid == "honeypy":
                if hostname:
                    settings["sensor_name"] = hostname
                if banners.get("http_title"):
                    settings["http_title"] = str(banners.get("http_title"))
                if fingerprints.get("paths"):
                    settings["fake_paths"] = copy_json(fingerprints.get("paths"))
                if banners.get("login_prompts"):
                    settings["login_prompts"] = copy_json(banners.get("login_prompts"))
            elif mid == "mailoney":
                if hostname:
                    settings["hostname"] = hostname
                if banners.get("smtp_banner"):
                    settings["smtp_banner"] = str(banners.get("smtp_banner"))
            elif mid == "glutton":
                settings["exposed_ports"] = copy_json(desired.get("exposed_ports", []))

        cowrie_settings = module_settings("cowrie", create=bool(cowrie))
        for key in ("hostname", "ssh_version", "userdb_entries"):
            if cowrie_settings is not None and key in cowrie:
                cowrie_settings[key] = str(cowrie.get(key) or "")
        if cowrie_settings is not None and "fake_http_html" in cowrie:
            cowrie_settings["fake_http_html"] = str(cowrie.get("fake_http_html") or "")
        if cowrie_settings is not None and "fake_ftp_files" in cowrie:
            cowrie_settings["fake_ftp_files"] = str(cowrie.get("fake_ftp_files") or "")

        honeypy_settings = module_settings("honeypy", create=bool(honeypy))
        for key in ("sensor_name", "raw_honeypy_yml"):
            if honeypy_settings is not None and key in honeypy:
                honeypy_settings[key] = str(honeypy.get(key) or "")

        mailoney_settings = module_settings("mailoney", create=bool(mailoney))
        for key in ("hostname", "smtp_banner", "raw_mailoney_cfg"):
            if mailoney_settings is not None and key in mailoney:
                mailoney_settings[key] = str(mailoney.get(key) or "")

        glutton_settings = module_settings("glutton", create=bool(glutton))
        if glutton_settings is not None and "raw_glutton_yml" in glutton:
            glutton_settings["raw_glutton_yml"] = str(glutton.get("raw_glutton_yml") or "")

        raw_key_by_module = {
            "cowrie": "raw_cowrie_cfg",
            "honeypy": "raw_honeypy_yml",
            "mailoney": "raw_mailoney_cfg",
            "glutton": "raw_glutton_yml",
        }
        for mid, value in raw_overrides.items():
            module_id = str(mid)
            settings = module_settings(module_id, create=module_id in module_index)
            if settings is None:
                continue
            raw_value = str(value or "")
            settings["raw_override"] = raw_value
            settings[raw_key_by_module.get(module_id, "raw_override")] = raw_value

        errors = policy_errors(policy, catalog)
        if errors:
            self.send_json({"status": "invalid_policy", "errors": errors}, HTTPStatus.BAD_REQUEST)
            return
        policy = self.save_policy(policy)
        self.send_json({"status": "saved", "policy": policy, "sensor_id": sensor_id})

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"center: {self.address_string()} - {fmt % args}")
