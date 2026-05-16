from __future__ import annotations

import json
import os
import platform
import time
from typing import Any, Callable


EventSender = Callable[[dict[str, Any]], bool]

RUNTIME_VERSION = "docker-runtime-v1"
PROJECT_PREFIX = "edc"
SUPPORTED_IMAGES = {
    "cowrie": "edc/cowrie:local",
    "conpot": "edc/conpot:local",
    "mailoney": "edc/mailoney:local",
    "honeypy": "edc/honeypy:local",
    "glutton": "edc/glutton:local",
}
UPSTREAM_IMAGES = {
    "cowrie": "arm32v7/debian:bookworm-slim",
    "conpot": "honeynet/conpot:latest",
    "mailoney": "python:3.11-slim",
    "honeypy": "python:2.7-slim-buster",
    "glutton": "golang:1.23-bookworm",
}
MODULE_LOG_HINTS = {
    "cowrie": "/home/cowrie/cowrie/var/log/cowrie/cowrie.json",
    "conpot": "/logs/conpot.json",
    "mailoney": "/logs/mailoney.jsonl",
    "honeypy": "/logs/honeypy-events.json",
    "glutton": "/logs/glutton.log",
}
ARM32_ARCHES = {"armv7l", "armv6l", "armhf", "armv7"}
ARM32_UNSUPPORTED_MODULES: set[str] = set()


def now_ts() -> float:
    return time.time()


def safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "-" for char in value).strip("-") or "sensor"


def yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def service_lookup(module: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(service.get("id")): service for service in module.get("services", [])}


def selected_host_port(module: dict[str, Any], service_id: str, default: int) -> int:
    service = service_lookup(module).get(service_id, {})
    return int(service.get("host_port") or service.get("default_host_port") or default)


def module_enabled(module: dict[str, Any]) -> bool:
    return module.get("enabled", True) is not False


def selected_services(module: dict[str, Any]) -> list[dict[str, Any]]:
    if not module_enabled(module):
        return []
    return [service for service in module.get("services", []) if service.get("enabled", True) is not False]


def selected_service_ids(module: dict[str, Any]) -> set[str]:
    return {str(service.get("id")) for service in selected_services(module)}


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def compose_service_name(module_id: str) -> str:
    return f"honeypot-{safe_name(module_id)}"


def sensor_architecture() -> str:
    return os.environ.get("EDC_SENSOR_ARCH") or platform.machine()


def module_supported_on_arch(module_id: str, architecture: str | None = None) -> tuple[bool, str]:
    _ = architecture or sensor_architecture()
    if module_id in ARM32_UNSUPPORTED_MODULES:
        return False, f"{module_id} disabled by runtime architecture policy"
    return True, ""
