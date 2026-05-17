from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

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
JSON_POST_PATHS = {"/api/events", "/api/sensors", "/api/mask", "/api/logs/batch", "/api/logs/events", "/api/logs/raw"}


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
        self.send_json(sensors_payload(policy, events, read_sensor_states(self.store_path)))

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
        policy.setdefault("sensors", []).append(sensor)
        errors = policy_errors(policy, catalog)
        if errors:
            self.send_json({"status": "invalid_policy", "errors": errors}, HTTPStatus.BAD_REQUEST)
            return
        policy = self.save_policy(policy)
        self.send_json({"status": "saved", "sensor": sensor, "policy": policy}, HTTPStatus.CREATED)

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

        def module_settings(mid: str) -> dict[str, Any]:
            module = module_index.get(mid)
            if not module:
                module = {"id": mid, "enabled": True, "services": [], "settings": {}}
                modules.append(module)
                module_index[mid] = module
            settings = module.setdefault("settings", {})
            return settings if isinstance(settings, dict) else {}

        cowrie = payload.get("cowrie") if isinstance(payload.get("cowrie"), dict) else {}
        honeypy = payload.get("honeypy") if isinstance(payload.get("honeypy"), dict) else {}
        mailoney = payload.get("mailoney") if isinstance(payload.get("mailoney"), dict) else {}
        glutton = payload.get("glutton") if isinstance(payload.get("glutton"), dict) else {}

        cowrie_settings = module_settings("cowrie")
        for key in ("hostname", "ssh_version", "userdb_entries"):
            if key in cowrie:
                cowrie_settings[key] = str(cowrie.get(key) or "")
        if "fake_http_html" in cowrie:
            cowrie_settings["fake_http_html"] = str(cowrie.get("fake_http_html") or "")
        if "fake_ftp_files" in cowrie:
            cowrie_settings["fake_ftp_files"] = str(cowrie.get("fake_ftp_files") or "")

        honeypy_settings = module_settings("honeypy")
        for key in ("sensor_name", "raw_honeypy_yml"):
            if key in honeypy:
                honeypy_settings[key] = str(honeypy.get(key) or "")

        mailoney_settings = module_settings("mailoney")
        for key in ("hostname", "smtp_banner", "raw_mailoney_cfg"):
            if key in mailoney:
                mailoney_settings[key] = str(mailoney.get(key) or "")

        glutton_settings = module_settings("glutton")
        if "raw_glutton_yml" in glutton:
            glutton_settings["raw_glutton_yml"] = str(glutton.get("raw_glutton_yml") or "")

        errors = policy_errors(policy, catalog)
        if errors:
            self.send_json({"status": "invalid_policy", "errors": errors}, HTTPStatus.BAD_REQUEST)
            return
        policy = self.save_policy(policy)
        self.send_json({"status": "saved", "policy": policy, "sensor_id": sensor_id})

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"center: {self.address_string()} - {fmt % args}")
