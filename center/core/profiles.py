from __future__ import annotations

import json
from typing import Any

from .policy import modules_by_id, services_by_id


DEFAULT_BUILTIN_PROFILES: dict[str, dict[str, Any]] = {
    "full_stack": {
        "title": "Full Stack",
        "description": "All supported honeypots enabled together for maximal coverage.",
        "desired_state": {
            "runtime_mode": "docker",
            "persona": {
                "hostname": "edge-gateway-01",
                "department": "Infrastructure",
                "os": "Debian GNU/Linux",
                "asset_tag": "EDGE-GW-01",
            },
            "modules": [
                {
                    "id": "cowrie",
                    "enabled": True,
                    "services": [
                        {"id": "ssh", "enabled": True, "host_port": 2222},
                        {"id": "telnet", "enabled": True, "host_port": 2223},
                    ],
                    "settings": {
                        "hostname": "edge-gateway-01",
                        "sensor_name": "edge-gateway-01",
                        "ssh_version": "SSH-2.0-OpenSSH_8.4",
                    },
                },
                {
                    "id": "opencanary",
                    "enabled": True,
                    "services": [
                        {"id": "http", "enabled": True, "host_port": 8081},
                        {"id": "ftp", "enabled": True, "host_port": 2121},
                        {"id": "smb", "enabled": True, "host_port": 1445},
                        {"id": "redis", "enabled": True, "host_port": 6379},
                        {"id": "mysql", "enabled": True, "host_port": 3306},
                    ],
                    "settings": {
                        "device.node_id": "opencanary-edge-gateway-01",
                        "http.banner": "nginx/1.18.0",
                        "http.skin": "nasLogin",
                    },
                },
                {
                    "id": "heralding",
                    "enabled": True,
                    "services": [
                        {"id": "ftp", "enabled": True, "host_port": 2122},
                        {"id": "http", "enabled": True, "host_port": 8082},
                        {"id": "pop3", "enabled": True, "host_port": 1110},
                        {"id": "smtp", "enabled": True, "host_port": 2525},
                    ],
                    "settings": {
                        "banner_profile": "enterprise-mail-and-ftp",
                        "enabled_protocols": "ftp,http,pop3,smtp",
                    },
                },
                {
                    "id": "conpot",
                    "enabled": True,
                    "services": [
                        {"id": "modbus", "enabled": True, "host_port": 1502},
                        {"id": "http", "enabled": True, "host_port": 8800},
                    ],
                    "settings": {"protocol_profile": "modbus-http"},
                },
                {
                    "id": "dionaea",
                    "enabled": True,
                    "services": [
                        {"id": "smb", "enabled": True, "host_port": 2445},
                        {"id": "http", "enabled": True, "host_port": 8083},
                        {"id": "ftp", "enabled": True, "host_port": 2123},
                    ],
                    "settings": {"services_enabled": "smb,http,ftp"},
                },
            ],
        },
    },
    "printer": {
        "title": "Office Printer",
        "description": "MFP/profile with web admin, SMB spool path, and maintenance SSH.",
        "desired_state": {
            "runtime_mode": "docker",
            "persona": {
                "hostname": "prn-mfp-01",
                "department": "Office",
                "os": "Embedded Linux",
                "asset_tag": "PRN-MFP-01",
            },
            "modules": [
                {
                    "id": "cowrie",
                    "enabled": True,
                    "services": [
                        {"id": "ssh", "enabled": True, "host_port": 22},
                        {"id": "telnet", "enabled": False, "host_port": 2323},
                    ],
                    "settings": {
                        "hostname": "prn-mfp-01",
                        "sensor_name": "prn-mfp-01",
                        "ssh_version": "SSH-2.0-OpenSSH_7.4p1 Debian-10+deb9u7",
                        "userdb_entries": "admin:x:admin\nservice:x:service\nroot:x:123456",
                    },
                },
                {
                    "id": "opencanary",
                    "enabled": True,
                    "services": [
                        {"id": "http", "enabled": True, "host_port": 80},
                        {"id": "ftp", "enabled": True, "host_port": 21},
                        {"id": "smb", "enabled": True, "host_port": 445},
                        {"id": "redis", "enabled": False, "host_port": 6379},
                        {"id": "mysql", "enabled": False, "host_port": 3306},
                    ],
                    "settings": {
                        "device.node_id": "opencanary-prn-mfp-01",
                        "http.banner": "HP Embedded Web Server",
                        "http.skin": "nasLogin",
                        "ftp.banner": "220 FTP Server ready",
                        "smb.auditfile": "/var/log/samba-audit.log",
                    },
                },
            ],
        },
    },
    "camera": {
        "title": "IP Camera",
        "description": "CCTV/profile with web console and maintenance shell footprint.",
        "desired_state": {
            "runtime_mode": "docker",
            "persona": {
                "hostname": "cam-lobby-01",
                "department": "Security",
                "os": "Embedded Linux",
                "asset_tag": "CCTV-LOBBY-01",
            },
            "modules": [
                {
                    "id": "cowrie",
                    "enabled": True,
                    "services": [
                        {"id": "ssh", "enabled": True, "host_port": 22},
                        {"id": "telnet", "enabled": False, "host_port": 2323},
                    ],
                    "settings": {
                        "hostname": "cam-lobby-01",
                        "sensor_name": "cam-lobby-01",
                        "ssh_version": "SSH-2.0-dropbear_2020.81",
                        "userdb_entries": "root:x:12345\nadmin:x:admin",
                    },
                },
                {
                    "id": "opencanary",
                    "enabled": True,
                    "services": [
                        {"id": "http", "enabled": True, "host_port": 80},
                        {"id": "ftp", "enabled": False, "host_port": 21},
                        {"id": "smb", "enabled": False, "host_port": 445},
                        {"id": "redis", "enabled": False, "host_port": 6379},
                        {"id": "mysql", "enabled": False, "host_port": 3306},
                    ],
                    "settings": {
                        "device.node_id": "opencanary-cam-lobby-01",
                        "http.banner": "Boa/0.94.14rc21",
                        "http.skin": "nasLogin",
                        "ftp.banner": "220 IPCamera FTP Server",
                    },
                },
            ],
        },
    },
    "backup_server": {
        "title": "Backup Server",
        "description": "Storage/backup node with SMB and legacy transfer services.",
        "desired_state": {
            "runtime_mode": "docker",
            "persona": {
                "hostname": "backup-srv-01",
                "department": "Infrastructure",
                "os": "Debian GNU/Linux",
                "asset_tag": "BCK-SRV-01",
            },
            "modules": [
                {
                    "id": "cowrie",
                    "enabled": True,
                    "services": [
                        {"id": "ssh", "enabled": True, "host_port": 22},
                        {"id": "telnet", "enabled": False, "host_port": 2223},
                    ],
                    "settings": {
                        "hostname": "backup-srv-01",
                        "sensor_name": "backup-srv-01",
                        "ssh_version": "SSH-2.0-OpenSSH_8.2p1 Ubuntu-4ubuntu0.5",
                        "userdb_entries": "root:x:backup\nbackup:x:backup123\nadmin:x:admin",
                    },
                },
                {
                    "id": "dionaea",
                    "enabled": True,
                    "services": [
                        {"id": "smb", "enabled": True, "host_port": 445},
                        {"id": "http", "enabled": True, "host_port": 8083},
                        {"id": "ftp", "enabled": True, "host_port": 21},
                    ],
                    "settings": {
                        "services_enabled": "smb,http,ftp",
                        "artifact_storage": "center",
                    },
                },
                {
                    "id": "heralding",
                    "enabled": True,
                    "services": [
                        {"id": "ftp", "enabled": True, "host_port": 2122},
                        {"id": "http", "enabled": False, "host_port": 8082},
                        {"id": "pop3", "enabled": True, "host_port": 1110},
                        {"id": "smtp", "enabled": True, "host_port": 2525},
                    ],
                    "settings": {
                        "banner_profile": "enterprise-mail-and-ftp",
                        "enabled_protocols": "ftp,pop3,smtp",
                    },
                },
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
            {
                "id": service["id"],
                "enabled": True,
                "host_port": service.get("default_host_port", service.get("container_port")),
            }
            for service in catalog_module.get("services", [])
        ],
        "settings": {
            field["key"]: field.get("default", "")
            for field in catalog_module.get("config_schema", [])
            if isinstance(field, dict) and field.get("key")
        },
    }


def _merge_module_template(module_template: dict[str, Any], catalog_module: dict[str, Any]) -> dict[str, Any]:
    module = _defaults_for_module(catalog_module)
    module["enabled"] = bool(module_template.get("enabled", True))
    if isinstance(module_template.get("settings"), dict):
        module["settings"].update(module_template["settings"])

    service_index = services_by_id(catalog_module)
    service_templates = {
        str(item.get("id")): item
        for item in module_template.get("services", [])
        if isinstance(item, dict) and item.get("id")
    }
    for service in module["services"]:
        override = service_templates.get(service["id"])
        if not override:
            continue
        if "enabled" in override:
            service["enabled"] = bool(override["enabled"])
        if "host_port" in override:
            service["host_port"] = override["host_port"]

    # Preserve custom known services if catalog grows and profile wants to pin one explicitly.
    for service_id, override in service_templates.items():
        if not service_index.get(service_id):
            continue
        if any(existing["id"] == service_id for existing in module["services"]):
            continue
        module["services"].append(
            {
                "id": service_id,
                "enabled": bool(override.get("enabled", True)),
                "host_port": override.get(
                    "host_port",
                    service_index[service_id].get("default_host_port", service_index[service_id].get("container_port")),
                ),
            }
        )
    return module


def _compile_profile_definition(profile_id: str, profile: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    desired = profile.get("desired_state", {})
    module_index = modules_by_id(catalog)
    compiled_modules: list[dict[str, Any]] = []
    for item in desired.get("modules", []):
        if not isinstance(item, dict):
            continue
        module_id = str(item.get("id") or "")
        catalog_module = module_index.get(module_id)
        if not catalog_module:
            continue
        compiled_modules.append(_merge_module_template(item, catalog_module))
    return {
        "id": profile_id,
        "title": str(profile.get("title") or profile_id),
        "description": str(profile.get("description") or ""),
        "desired_state": {
            "profile": profile_id,
            "runtime_mode": desired.get("runtime_mode", "docker"),
            "persona": _deep_copy(desired.get("persona", {})),
            "modules": compiled_modules,
        },
    }


def available_profiles(policy: dict[str, Any], catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    custom = policy.get("profiles", {})
    if not isinstance(custom, dict):
        custom = {}
    combined = {**DEFAULT_BUILTIN_PROFILES, **custom}
    return {
        profile_id: _compile_profile_definition(profile_id, profile, catalog)
        for profile_id, profile in combined.items()
        if isinstance(profile_id, str) and profile_id and isinstance(profile, dict)
    }


def apply_profile(policy: dict[str, Any], catalog: dict[str, Any], sensor: dict[str, Any], profile_id: str) -> tuple[bool, str]:
    profiles = available_profiles(policy, catalog)
    selected = profiles.get(profile_id)
    if not selected:
        return False, "profile not found"
    sensor["desired_state"] = _deep_copy(selected["desired_state"])
    return True, ""
