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
    "cowrie": "cowrie/cowrie:latest",
    "opencanary": "thinkst/opencanary:latest",
    "dionaea": "dinotools/dionaea:latest",
    "conpot": "honeynet/conpot:latest",
    "heralding": "dtagdevsec/heralding:24.04.1",
}
MODULE_LOG_HINTS = {
    "cowrie": "/cowrie/cowrie-git/var/log/cowrie/cowrie.json",
    "opencanary": "/var/tmp/opencanary.log",
    "dionaea": "/opt/dionaea/var/log/dionaea",
    "conpot": "container stdout",
    "heralding": "container stdout",
}
HERALDING_CAPABILITIES = {
    "ftp": 21,
    "telnet": 23,
    "pop3": 110,
    "pop3s": 995,
    "postgresql": 5432,
    "imap": 143,
    "imaps": 993,
    "ssh": 22,
    "http": 80,
    "https": 443,
    "smtp": 25,
    "smtps": 465,
    "vnc": 5900,
    "socks5": 1080,
    "mysql": 3306,
    "rdp": 3389,
}
ARM32_ARCHES = {"armv7l", "armv6l", "armhf", "armv7"}
ARM32_UNSUPPORTED_MODULES = set(SUPPORTED_IMAGES)


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
    arch = architecture or sensor_architecture()
    if arch in ARM32_ARCHES and module_id in ARM32_UNSUPPORTED_MODULES and os.environ.get("EDC_ENABLE_UNTESTED_ARM_IMAGES") != "1":
        return (
            False,
            f"{module_id} отключён на 32-bit ARM ({arch}): текущий Docker image не публикует linux/arm/v7 manifest. "
            "Задайте EDC_ENABLE_UNTESTED_ARM_IMAGES=1 только если вручную указали совместимый образ.",
        )
    return True, ""
