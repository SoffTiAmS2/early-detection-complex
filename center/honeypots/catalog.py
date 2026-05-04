"""Supported honeypot catalog used by manager and generator."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SERVICE_CATALOG: dict[str, dict[str, Any]] = {
    "ssh": {
        "title": "SSH",
        "protocol": "ssh",
        "container_port": 2222,
        "default_host_port": 2222,
    },
    "telnet": {
        "title": "Telnet",
        "protocol": "telnet",
        "container_port": 2223,
        "default_host_port": 2223,
    },
}


HONEYPOT_CATALOG: dict[str, dict[str, Any]] = {
    "cowrie": {
        "title": "Cowrie",
        "image": "cowrie/cowrie:latest",
        "role": "office",
        "description": "Настоящая SSH/Telnet-приманка Cowrie на базе официального Docker-образа.",
        "default_services": ["ssh", "telnet"],
        "services": ["ssh", "telnet"],
        "settings": [
            {"key": "hostname", "title": "Фейковое имя узла", "type": "text", "default": "srv01"},
            {"key": "ssh_version", "title": "Версия SSH", "type": "text", "default": "SSH-2.0-OpenSSH_8.4"},
            {"key": "backend", "title": "Режим", "type": "select", "default": "shell", "options": ["shell", "proxy"]},
            {"key": "auth_class", "title": "Правило входа", "type": "select", "default": "UserDB", "options": ["UserDB", "AuthRandom"]},
            {"key": "download_limit_size", "title": "Лимит загрузки, байт", "type": "number", "default": 10485760},
            {"key": "sftp_enabled", "title": "Включить SFTP", "type": "boolean", "default": True},
        ],
    },
}


def default_settings(honeypot_type: str) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    for field in HONEYPOT_CATALOG[honeypot_type]["settings"]:
        settings[field["key"]] = deepcopy(field.get("default"))
    return settings


def default_service(service_name: str) -> dict[str, Any]:
    service = SERVICE_CATALOG[service_name]
    return {
        "name": service_name,
        "enabled": True,
        "host_port": service["default_host_port"],
    }


def default_honeypot(honeypot_type: str) -> dict[str, Any]:
    item = HONEYPOT_CATALOG[honeypot_type]
    return {
        "type": honeypot_type,
        "enabled": True,
        "services": [default_service(service) for service in item["default_services"]],
        "settings": default_settings(honeypot_type),
    }


def normalize_service(raw: Any, honeypot_type: str) -> dict[str, Any] | None:
    """Normalize legacy string services and new service objects."""

    if isinstance(raw, str):
        service_name = raw
        data = default_service(service_name) if service_name in SERVICE_CATALOG else None
    elif isinstance(raw, dict):
        service_name = str(raw.get("name", ""))
        data = default_service(service_name) if service_name in SERVICE_CATALOG else None
        if data:
            data["enabled"] = raw.get("enabled", True) is not False
            data["host_port"] = raw.get("host_port", data["host_port"])
    else:
        return None

    if not data or service_name not in HONEYPOT_CATALOG[honeypot_type]["services"]:
        return None
    try:
        data["host_port"] = int(data["host_port"])
    except (TypeError, ValueError):
        data["host_port"] = SERVICE_CATALOG[service_name]["default_host_port"]
    return data


def legacy_honeypot(profile: str, services: list[Any] | None = None) -> dict[str, Any]:
    honeypot_type = profile if profile in HONEYPOT_CATALOG else "cowrie"
    honeypot = default_honeypot(honeypot_type)
    if services:
        normalized = [normalize_service(service, honeypot_type) for service in services]
        honeypot["services"] = [service for service in normalized if service]
    return honeypot


def catalog_payload() -> dict[str, Any]:
    return {
        "honeypots": HONEYPOT_CATALOG,
        "services": {
            key: {
                "title": value["title"],
                "protocol": value["protocol"],
                "container_port": value["container_port"],
                "default_host_port": value["default_host_port"],
            }
            for key, value in SERVICE_CATALOG.items()
        },
    }
