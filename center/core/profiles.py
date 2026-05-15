from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import DEFAULT_DEVICE_PROFILES
from .policy import modules_by_id, services_by_id
from .utils import load_json


def _deep_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def load_device_profile_catalog(path: Path | str = DEFAULT_DEVICE_PROFILES) -> dict[str, Any]:
    return load_json(Path(path))


def _schema_defaults(catalog_module: dict[str, Any]) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    for field in catalog_module.get("config_schema", []):
        if isinstance(field, dict) and field.get("key"):
            settings[str(field["key"])] = _deep_copy(field.get("default", ""))
    return settings


def _profile_id(profile: dict[str, Any]) -> str:
    return str(profile.get("id") or profile.get("name") or "").strip()


def profile_errors(profile: dict[str, Any], catalog: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    profile_id = _profile_id(profile) or "<unknown>"
    module_index = modules_by_id(catalog)

    if not _profile_id(profile):
        errors.append("profile id is required")
    if not isinstance(profile.get("exposed_ports"), list):
        errors.append(f"{profile_id}: exposed_ports must be a list")
        return errors

    seen_ports: set[tuple[str, int]] = set()
    for item in profile.get("exposed_ports", []):
        if not isinstance(item, dict):
            errors.append(f"{profile_id}: exposed port must be an object")
            continue
        module_id = str(item.get("honeypot") or "").strip()
        service_id = str(item.get("module_service") or item.get("service") or "").strip()
        protocol = str(item.get("protocol") or "tcp").strip().lower()
        try:
            host_port = int(item.get("port"))
        except (TypeError, ValueError):
            errors.append(f"{profile_id}: {module_id}/{service_id}: port must be an integer")
            continue
        if not 1 <= host_port <= 65535:
            errors.append(f"{profile_id}: {module_id}/{service_id}: port out of range")
        key = (protocol, host_port)
        if key in seen_ports:
            errors.append(f"{profile_id}: duplicate exposed port {protocol}/{host_port}")
        seen_ports.add(key)
        catalog_module = module_index.get(module_id)
        if not catalog_module:
            errors.append(f"{profile_id}: unknown honeypot module: {module_id}")
            continue
        if service_id not in services_by_id(catalog_module):
            errors.append(f"{profile_id}: {module_id}: unknown service: {service_id}")
    return errors


def _module_settings(profile: dict[str, Any], catalog_module: dict[str, Any]) -> dict[str, Any]:
    module_id = str(catalog_module.get("id"))
    profile_id = _profile_id(profile)
    legend = profile.get("legend") if isinstance(profile.get("legend"), dict) else {}
    banners = profile.get("banners") if isinstance(profile.get("banners"), dict) else {}
    fingerprints = profile.get("service_fingerprints") if isinstance(profile.get("service_fingerprints"), dict) else {}
    templates = profile.get("config_templates") if isinstance(profile.get("config_templates"), dict) else {}
    resource_limits = profile.get("resource_limits") if isinstance(profile.get("resource_limits"), dict) else {}
    exposed_ports = [item for item in profile.get("exposed_ports", []) if isinstance(item, dict) and item.get("honeypot") == module_id]

    settings = _schema_defaults(catalog_module)
    settings.update(
        {
            "profile_id": profile_id,
            "profile_name": profile.get("name") or profile.get("title") or profile_id,
            "device_type": profile.get("device_type", ""),
            "template_id": templates.get(module_id, profile_id),
            "resource_limits": _deep_copy(resource_limits),
        }
    )

    hostname = str(banners.get("hostname") or legend.get("hostname") or profile_id)
    if module_id == "cowrie":
        settings["hostname"] = hostname
        settings["ssh_version"] = str(banners.get("ssh_banner") or banners.get("telnet_banner") or settings.get("ssh_version") or "SSH-2.0-OpenSSH_8.4")
        settings.setdefault("userdb_entries", "root:x:!root\nadmin:x:admin")
    elif module_id == "mailoney":
        settings["hostname"] = hostname
        settings["smtp_banner"] = str(banners.get("smtp_banner") or f"220 {hostname} ESMTP")
    elif module_id == "honeypy":
        settings["sensor_name"] = hostname
        settings["http_title"] = str(banners.get("http_title") or profile.get("title") or hostname)
        settings["fake_paths"] = _deep_copy(fingerprints.get("paths", []))
        settings["login_prompts"] = _deep_copy(banners.get("login_prompts", []))
        settings["banners"] = _deep_copy(banners)
        settings["service_fingerprints"] = _deep_copy(fingerprints)
    elif module_id == "glutton":
        settings["exposed_ports"] = _deep_copy(exposed_ports)
        settings["banners"] = _deep_copy(banners)
        settings["service_fingerprints"] = _deep_copy(fingerprints)
    elif module_id == "conpot":
        settings["template"] = str(templates.get("conpot") or settings.get("template") or "default")
        settings["banners"] = _deep_copy(banners)
        settings["service_fingerprints"] = _deep_copy(fingerprints)

    return settings


def render_profile_desired_state(profile: dict[str, Any], catalog: dict[str, Any], config_version: int | None = None) -> dict[str, Any]:
    profile_id = _profile_id(profile)
    module_index = modules_by_id(catalog)
    grouped: dict[str, list[dict[str, Any]]] = {}

    for item in profile.get("exposed_ports", []):
        if not isinstance(item, dict):
            continue
        module_id = str(item.get("honeypot") or "").strip()
        service_id = str(item.get("module_service") or item.get("service") or "").strip()
        if module_id not in module_index:
            continue
        catalog_service = services_by_id(module_index[module_id]).get(service_id)
        if not catalog_service:
            continue
        grouped.setdefault(module_id, []).append(
            {
                "id": service_id,
                "enabled": True,
                "host_port": int(item.get("port")),
                "profile_service": item.get("service", service_id),
                "description": item.get("description", ""),
            }
        )

    modules = []
    for module_id in profile.get("honeypots", []):
        catalog_module = module_index.get(str(module_id))
        if not catalog_module:
            continue
        services = grouped.get(str(module_id), [])
        if not services:
            continue
        modules.append(
            {
                "id": str(module_id),
                "enabled": True,
                "services": services,
                "settings": _module_settings(profile, catalog_module),
            }
        )

    services_summary = []
    for module in modules:
        ports = {str(service["host_port"]): service.get("id") for service in module.get("services", [])}
        templates = profile.get("config_templates") if isinstance(profile.get("config_templates"), dict) else {}
        services_summary.append(
            {
                "name": module["id"],
                "enabled": True,
                "ports": ports,
                "template": templates.get(module["id"]),
            }
        )

    version = int(config_version or profile.get("version") or 1)
    return {
        "runtime_mode": "docker",
        "active_profile": profile_id,
        "profile": profile_id,
        "profile_name": profile.get("name") or profile.get("title") or profile_id,
        "device_type": profile.get("device_type", ""),
        "config_version": version,
        "persona": _deep_copy(profile.get("legend", {})),
        "legend": _deep_copy(profile.get("legend", {})),
        "exposed_ports": _deep_copy(profile.get("exposed_ports", [])),
        "honeypots": _deep_copy(profile.get("honeypots", [])),
        "banners": _deep_copy(profile.get("banners", {})),
        "service_fingerprints": _deep_copy(profile.get("service_fingerprints", {})),
        "docker_template": _deep_copy(profile.get("docker_template", {})),
        "config_templates": _deep_copy(profile.get("config_templates", {})),
        "resource_limits": _deep_copy(profile.get("resource_limits", {})),
        "logging": _deep_copy(profile.get("logging", {"raw": True, "normalized": True})),
        "services": services_summary,
        "modules": modules,
    }


def _catalog_profiles(profile_catalog: dict[str, Any], catalog: dict[str, Any], config_version: int) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for profile in profile_catalog.get("profiles", []):
        if not isinstance(profile, dict):
            continue
        profile_id = _profile_id(profile)
        if not profile_id:
            continue
        errors = profile_errors(profile, catalog)
        profiles[profile_id] = {
            **_deep_copy(profile),
            "id": profile_id,
            "title": profile.get("title") or profile.get("name") or profile_id,
            "source": "catalog",
            "errors": errors,
            "desired_state": render_profile_desired_state(profile, catalog, config_version),
        }
    return profiles


def _policy_profiles(policy: dict[str, Any], catalog: dict[str, Any], config_version: int) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for profile in policy.get("profiles", []):
        if not isinstance(profile, dict):
            continue
        profile_id = _profile_id(profile)
        if not profile_id:
            continue
        if isinstance(profile.get("desired_state"), dict):
            desired_state = _deep_copy(profile["desired_state"])
            desired_state.setdefault("profile", profile_id)
            desired_state.setdefault("active_profile", profile_id)
            desired_state.setdefault("config_version", config_version)
            errors: list[str] = []
        else:
            errors = profile_errors(profile, catalog)
            desired_state = render_profile_desired_state(profile, catalog, config_version)
        profiles[profile_id] = {
            **_deep_copy(profile),
            "id": profile_id,
            "title": profile.get("title") or profile.get("name") or profile_id,
            "source": "policy",
            "errors": errors,
            "desired_state": desired_state,
        }
    return profiles


def available_profiles(
    policy: dict[str, Any],
    catalog: dict[str, Any],
    profile_catalog: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    config_version = int(policy.get("version", 1))
    profile_catalog = profile_catalog if isinstance(profile_catalog, dict) else load_device_profile_catalog()
    profiles = _catalog_profiles(profile_catalog, catalog, config_version)
    profiles.update(_policy_profiles(policy, catalog, config_version))
    return profiles


def apply_profile(
    policy: dict[str, Any],
    catalog: dict[str, Any],
    sensor: dict[str, Any],
    profile_id: str,
    profile_catalog: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    profiles = available_profiles(policy, catalog, profile_catalog)
    selected = profiles.get(profile_id)
    if not selected:
        return False, f"unknown profile_id: {profile_id}"
    if selected.get("errors"):
        return False, "; ".join(str(item) for item in selected["errors"])
    next_version = int(policy.get("version", 1)) + 1
    desired_state = _deep_copy(selected["desired_state"])
    desired_state["active_profile"] = profile_id
    desired_state["profile"] = profile_id
    desired_state["config_version"] = next_version
    sensor["active_profile"] = profile_id
    sensor["desired_state"] = desired_state
    return True, ""
