from __future__ import annotations

import json
import platform
import socket
import time
from pathlib import Path
from typing import Any


def now_ts() -> float:
    return time.time()


def host_facts() -> dict[str, Any]:
    return {
        "hostname": socket.gethostname(),
        "architecture": platform.machine(),
        "platform": platform.platform(),
        "python": platform.python_version(),
    }


def enroll_event(sensor_id: str, agent_version: str) -> dict[str, Any]:
    facts = host_facts()
    return {
        "event_type": "sensor.enroll",
        "timestamp": now_ts(),
        "sensor_id": sensor_id,
        "status": "enrolling",
        "agent_version": agent_version,
        "node_hostname": facts["hostname"],
        "architecture": facts["architecture"],
        "facts": facts,
    }


def module_plan(desired: dict[str, Any]) -> list[dict[str, Any]]:
    plan = []
    for module in desired.get("modules", []):
        enabled = module.get("enabled", True) is not False
        services = []
        for service in module.get("services", []):
            service_enabled = enabled and service.get("enabled", True) is not False
            services.append(
                {
                    "id": service.get("id"),
                    "protocol": service.get("protocol", "tcp"),
                    "host_port": service.get("host_port"),
                    "container_port": service.get("container_port", service.get("host_port")),
                    "state": "planned" if service_enabled else "disabled",
                }
            )
        plan.append(
            {
                "id": module.get("id"),
                "title": module.get("title"),
                "enabled": enabled,
                "status": "planned" if enabled else "disabled",
                "runtime": module.get("runtime"),
                "resource_class": module.get("resource_class"),
                "settings": module.get("settings", {}),
                "services": services,
            }
        )
    return plan


def runtime_plan(
    plan: list[dict[str, Any]],
    active_services: list[dict[str, Any]],
    listener_errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    active = {(item["module"], item["service"], item["host_port"]): item for item in active_services}
    failed = {
        (item["module"], item["service"], item["host_port"])
        for item in listener_errors
        if item.get("module") and item.get("service") and item.get("host_port") is not None
    }
    module_skips = {
        item.get("module"): item
        for item in listener_errors
        if item.get("module") and item.get("stage") == "architecture"
    }
    updated: list[dict[str, Any]] = []
    for module in plan:
        module_copy = {**module, "services": []}
        service_states = []
        for service in module["services"]:
            key = (module["id"], service["id"], service["host_port"])
            service_copy = {**service}
            if key in active:
                service_copy["state"] = "listening" if active[key].get("running") is True else str(active[key].get("state") or "unknown")
                if active[key].get("container_port") is not None:
                    service_copy["container_port"] = active[key]["container_port"]
                copy_runtime_fields(service_copy, active[key])
            elif key in failed:
                service_copy["state"] = "failed"
            elif module["id"] in module_skips:
                service_copy["state"] = "skipped"
                service_copy["last_error"] = module_skips[module["id"]].get("error")
            else:
                service_copy["state"] = "disabled" if not module["enabled"] else "pending"
            service_states.append(service_copy["state"])
            module_copy["services"].append(service_copy)
        if not module["enabled"]:
            module_copy["status"] = "disabled"
        elif module["id"] in module_skips:
            module_copy["status"] = "skipped"
        elif service_states and all(state == "listening" for state in service_states):
            module_copy["status"] = "running"
        elif any(state not in {"listening", "disabled", "pending"} for state in service_states):
            module_copy["status"] = "degraded"
        else:
            module_copy["status"] = "pending"
        updated.append(module_copy)
    return updated


def copy_runtime_fields(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in (
        "container_status",
        "container_state",
        "image",
        "running",
        "restart_count",
        "last_error",
        "port_bindings",
    ):
        if source.get(key) is not None:
            target[key] = source[key]


def write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def desired_signature(desired: dict[str, Any]) -> str:
    return json.dumps(desired, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def status_event(
    sensor_id: str,
    desired: dict[str, Any],
    plan: list[dict[str, Any]],
    agent_mode: str,
    agent_version: str,
    active_services: list[dict[str, Any]] | None = None,
    listener_errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    enabled_modules = [module for module in plan if module["enabled"]]
    planned_ports = [
        service["host_port"]
        for module in enabled_modules
        for service in module["services"]
        if service.get("host_port") is not None
    ]
    return {
        "event_type": "sensor.status",
        "timestamp": now_ts(),
        "sensor_id": sensor_id,
        "status": "online",
        "agent_mode": agent_mode,
        "agent_version": agent_version,
        "applied_version": desired.get("version"),
        "profile": desired.get("profile"),
        "persona": desired.get("persona", {}),
        "host": desired.get("host"),
        "architecture": desired.get("architecture"),
        "enabled_modules": [module["id"] for module in enabled_modules],
        "planned_ports": planned_ports,
        "active_services": active_services or [],
        "listener_errors": listener_errors or [],
        "modules": plan,
    }
