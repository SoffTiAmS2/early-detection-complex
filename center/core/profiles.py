from __future__ import annotations

import json
from typing import Any

from .policy import modules_by_id, services_by_id


DEFAULT_BUILTIN_PROFILES: dict[str, dict[str, Any]] = {
    "full_stack": {
        "title": "Full Stack",
        "description": "Cowrie + Conpot + Mailoney + HoneyPy + Glutton.",
        "desired_state": {
            "runtime_mode": "docker",
            "persona": {"hostname": "edge-gateway-01", "department": "Infrastructure", "os": "Debian GNU/Linux", "asset_tag": "EDGE-GW-01"},
            "modules": [
                {"id": "cowrie", "enabled": True, "services": [{"id": "ssh", "enabled": True, "host_port": 2222}, {"id": "telnet", "enabled": True, "host_port": 2223}], "settings": {"hostname": "edge-gateway-01"}},
                {"id": "conpot", "enabled": True, "services": [{"id": "modbus", "enabled": True, "host_port": 15020}, {"id": "s7comm", "enabled": True, "host_port": 10102}, {"id": "bacnet", "enabled": True, "host_port": 47808}, {"id": "http", "enabled": True, "host_port": 8800}], "settings": {"template": "default"}},
                {"id": "mailoney", "enabled": True, "services": [{"id": "smtp", "enabled": True, "host_port": 2525}], "settings": {"hostname": "mail-gw-01"}},
                {"id": "honeypy", "enabled": True, "services": [{"id": "http", "enabled": True, "host_port": 8082}, {"id": "mysql", "enabled": True, "host_port": 3307}, {"id": "redis", "enabled": True, "host_port": 6380}, {"id": "ftp", "enabled": True, "host_port": 2124}, {"id": "telnet", "enabled": True, "host_port": 2324}], "settings": {"sensor_name": "web-stack-01"}},
                {"id": "glutton", "enabled": True, "services": [{"id": "docker_api", "enabled": True, "host_port": 2375}, {"id": "mqtt", "enabled": True, "host_port": 1883}, {"id": "k8s_api", "enabled": True, "host_port": 6443}, {"id": "rdp", "enabled": True, "host_port": 3389}, {"id": "vnc", "enabled": True, "host_port": 5900}, {"id": "sip", "enabled": True, "host_port": 5060}], "settings": {}}
            ],
        },
    },
    "printer": {
        "title": "Printer",
        "description": "Printer-like mask with management access and SMTP trap.",
        "desired_state": {
            "runtime_mode": "docker",
            "persona": {"hostname": "prn-mfp-01", "department": "Office", "os": "Embedded Linux", "asset_tag": "PRN-MFP-01"},
            "modules": [
                {"id": "cowrie", "enabled": True, "services": [{"id": "ssh", "enabled": True, "host_port": 22}, {"id": "telnet", "enabled": False, "host_port": 2223}], "settings": {"hostname": "prn-mfp-01", "ssh_version": "SSH-2.0-OpenSSH_7.4p1 Debian-10+deb9u7"}},
                {"id": "honeypy", "enabled": True, "services": [{"id": "http", "enabled": True, "host_port": 80}, {"id": "ftp", "enabled": True, "host_port": 21}, {"id": "mysql", "enabled": False, "host_port": 3307}, {"id": "redis", "enabled": False, "host_port": 6380}, {"id": "telnet", "enabled": False, "host_port": 2324}], "settings": {"sensor_name": "printer-web-01"}},
                {"id": "mailoney", "enabled": True, "services": [{"id": "smtp", "enabled": True, "host_port": 25}], "settings": {"hostname": "mail-relay-prn-01"}}
            ],
        },
    },
    "camera": {
        "title": "Camera",
        "description": "IP-camera style profile with lightweight protocol set.",
        "desired_state": {
            "runtime_mode": "docker",
            "persona": {"hostname": "cam-lobby-01", "department": "Security", "os": "Embedded Linux", "asset_tag": "CCTV-LOBBY-01"},
            "modules": [
                {"id": "cowrie", "enabled": True, "services": [{"id": "ssh", "enabled": True, "host_port": 22}, {"id": "telnet", "enabled": False, "host_port": 2223}], "settings": {"hostname": "cam-lobby-01", "ssh_version": "SSH-2.0-dropbear_2020.81"}},
                {"id": "honeypy", "enabled": True, "services": [{"id": "http", "enabled": True, "host_port": 80}, {"id": "ftp", "enabled": False, "host_port": 2124}, {"id": "mysql", "enabled": False, "host_port": 3307}, {"id": "redis", "enabled": False, "host_port": 6380}, {"id": "telnet", "enabled": False, "host_port": 2324}], "settings": {"sensor_name": "camera-ui-01"}}
            ],
        },
    },
    "backup_server": {
        "title": "Backup Server",
        "description": "Storage/backup footprint with broader protocol exposure.",
        "desired_state": {
            "runtime_mode": "docker",
            "persona": {"hostname": "backup-srv-01", "department": "Infrastructure", "os": "Debian GNU/Linux", "asset_tag": "BCK-SRV-01"},
            "modules": [
                {"id": "cowrie", "enabled": True, "services": [{"id": "ssh", "enabled": True, "host_port": 22}, {"id": "telnet", "enabled": False, "host_port": 2223}], "settings": {"hostname": "backup-srv-01"}},
                {"id": "glutton", "enabled": True, "services": [{"id": "docker_api", "enabled": True, "host_port": 2375}, {"id": "mqtt", "enabled": True, "host_port": 1883}, {"id": "k8s_api", "enabled": False, "host_port": 6443}, {"id": "rdp", "enabled": True, "host_port": 3389}, {"id": "vnc", "enabled": True, "host_port": 5900}, {"id": "sip", "enabled": False, "host_port": 5060}], "settings": {}},
                {"id": "mailoney", "enabled": True, "services": [{"id": "smtp", "enabled": True, "host_port": 25}], "settings": {"hostname": "mail-backup-01"}}
            ],
        },
    },
}


def _deep_copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _defaults_for_module(catalog_module: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": catalog_module["id"],
        "enabled": True,
        "services": [
            {"id": service["id"], "enabled": True, "host_port": service.get("default_host_port", service.get("container_port"))}
            for service in catalog_module.get("services", [])
        ],
        "settings": {field["key"]: field.get("default", "") for field in catalog_module.get("config_schema", []) if isinstance(field, dict) and field.get("key")},
    }


def _merge_module(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = _deep_copy(base)
    merged["enabled"] = bool(override.get("enabled", merged.get("enabled", True)))
    services = {str(item.get("id")): item for item in merged.get("services", [])}
    for service in override.get("services", []):
        service_id = str(service.get("id"))
        if service_id not in services:
            services[service_id] = {"id": service_id, "enabled": True}
        services[service_id]["enabled"] = bool(service.get("enabled", services[service_id].get("enabled", True)))
        if "host_port" in service:
            services[service_id]["host_port"] = int(service["host_port"])
    merged["services"] = list(services.values())
    settings = merged.setdefault("settings", {})
    settings.update(override.get("settings", {}))
    return merged


def _apply_profile_template(catalog: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    module_index = modules_by_id(catalog)
    base_modules = {_id: _defaults_for_module(module) for _id, module in module_index.items()}
    desired_template = template.get("desired_state", {})
    module_overrides = desired_template.get("modules", [])
    service_templates = {str(item.get("id")): item for item in module_overrides}
    merged_modules = []
    for module_id, base in base_modules.items():
        override = service_templates.get(module_id)
        merged_modules.append(_merge_module(base, override) if override else base)
    for module_id, override in service_templates.items():
        if module_id not in base_modules:
            fallback_services = []
            catalog_module = module_index.get(module_id)
            if catalog_module:
                fallback_services = [{"id": service_id, "enabled": True, "host_port": service.get("default_host_port", service.get("container_port"))} for service_id, service in services_by_id(catalog_module).items()]
            merged_modules.append({"id": module_id, "enabled": bool(override.get("enabled", True)), "services": _deep_copy(override.get("services", fallback_services)), "settings": _deep_copy(override.get("settings", {}))})
    return {"runtime_mode": desired_template.get("runtime_mode", "docker"), "persona": _deep_copy(desired_template.get("persona", {})), "modules": merged_modules}


def available_profiles(policy: dict[str, Any], catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for profile_id, template in DEFAULT_BUILTIN_PROFILES.items():
        profiles[profile_id] = {
            "id": profile_id,
            "title": template.get("title", profile_id),
            "description": template.get("description", ""),
            "desired_state": _apply_profile_template(catalog, template),
            "source": "builtin",
        }
    for profile in policy.get("profiles", []):
        profile_id = str(profile.get("id", "")).strip()
        if not profile_id:
            continue
        if not isinstance(profile.get("desired_state"), dict):
            continue
        profiles[profile_id] = {
            "id": profile_id,
            "title": str(profile.get("title") or profile_id),
            "description": str(profile.get("description") or ""),
            "desired_state": _deep_copy(profile["desired_state"]),
            "source": "policy",
        }
    return profiles


def apply_profile(policy: dict[str, Any], catalog: dict[str, Any], sensor: dict[str, Any], profile_id: str) -> tuple[bool, str]:
    profiles = available_profiles(policy, catalog)
    selected = profiles.get(profile_id)
    if not selected:
        return False, f"unknown profile_id: {profile_id}"
    sensor["desired_state"] = _deep_copy(selected["desired_state"])
    sensor["desired_state"]["profile"] = profile_id
    return True, ""

