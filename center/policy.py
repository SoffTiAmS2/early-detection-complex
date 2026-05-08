from __future__ import annotations

import json
from typing import Any

from .utils import now_ts

def bump_policy_version(policy: dict[str, Any]) -> dict[str, Any]:
    updated = json.loads(json.dumps(policy))
    try:
        version = int(updated.get("version", 0))
    except (TypeError, ValueError):
        version = 0
    updated["version"] = version + 1
    updated["updated_at"] = now_ts()
    return updated

def modules_by_id(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {module["id"]: module for module in catalog.get("modules", [])}


def services_by_id(module: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {service["id"]: service for service in module.get("services", [])}


def settings_schema_by_key(module: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {field["key"]: field for field in module.get("config_schema", []) if isinstance(field, dict) and field.get("key")}


def validate_module_settings(sensor_id: str, module_id: str, settings: Any, catalog_module: dict[str, Any]) -> list[str]:
    if settings is None:
        return []
    if not isinstance(settings, dict):
        return [f"{sensor_id}: {module_id}: settings must be an object"]
    errors: list[str] = []
    schema = settings_schema_by_key(catalog_module)
    for key, value in settings.items():
        field = schema.get(str(key))
        if not field:
            continue
        field_type = field.get("type", "string")
        if field_type in {"string", "textarea", "list"}:
            if not isinstance(value, (str, list)):
                errors.append(f"{sensor_id}: {module_id}: setting {key} must be text")
            continue
        if field_type == "boolean":
            if not isinstance(value, bool):
                errors.append(f"{sensor_id}: {module_id}: setting {key} must be boolean")
            continue
        if field_type == "integer":
            try:
                numeric = int(value)
            except (TypeError, ValueError):
                errors.append(f"{sensor_id}: {module_id}: setting {key} must be integer")
                continue
            if "min" in field and numeric < int(field["min"]):
                errors.append(f"{sensor_id}: {module_id}: setting {key} must be >= {field['min']}")
            if "max" in field and numeric > int(field["max"]):
                errors.append(f"{sensor_id}: {module_id}: setting {key} must be <= {field['max']}")
            continue
        if field_type == "select":
            options = [str(item) for item in field.get("options", [])]
            if options and str(value) not in options:
                errors.append(f"{sensor_id}: {module_id}: setting {key} must be one of {', '.join(options)}")
    return errors


def policy_errors(policy: Any, catalog: Any) -> list[str]:
    """Validate the site policy before the center publishes desired state."""

    errors: list[str] = []
    if not isinstance(catalog, dict):
        return ["catalog must be an object"]
    if not isinstance(policy, dict):
        return ["policy must be an object"]

    module_index: dict[str, dict[str, Any]] = {}
    for module in catalog.get("modules", []):
        if not isinstance(module, dict):
            errors.append("catalog module must be an object")
            continue
        module_id = module.get("id")
        if not isinstance(module_id, str) or not module_id:
            errors.append("catalog module id must be a non-empty string")
            continue
        if module_id in module_index:
            errors.append(f"duplicate catalog module: {module_id}")
        module_index[module_id] = module

    sensors = policy.get("sensors")
    if not isinstance(sensors, list) or not sensors:
        errors.append("policy must contain at least one sensor")
        return errors

    seen_sensors: set[str] = set()
    for sensor in sensors:
        if not isinstance(sensor, dict):
            errors.append("sensor must be an object")
            continue
        sensor_id = sensor.get("id")
        if not isinstance(sensor_id, str) or not sensor_id:
            errors.append("sensor id must be a non-empty string")
            continue
        if sensor_id in seen_sensors:
            errors.append(f"duplicate sensor id: {sensor_id}")
        seen_sensors.add(sensor_id)

        desired = sensor.get("desired_state")
        if not isinstance(desired, dict):
            errors.append(f"{sensor_id}: desired_state must be an object")
            continue
        modules = desired.get("modules")
        if not isinstance(modules, list):
            errors.append(f"{sensor_id}: desired_state.modules must be a list")
            continue

        used_ports: dict[int, str] = {}
        for item in modules:
            if not isinstance(item, dict):
                errors.append(f"{sensor_id}: module must be an object")
                continue
            module_id = item.get("id")
            catalog_module = module_index.get(str(module_id))
            if not catalog_module:
                errors.append(f"{sensor_id}: unknown module: {module_id}")
                continue
            service_index = services_by_id(catalog_module)
            services = item.get("services")
            if not isinstance(services, list):
                errors.append(f"{sensor_id}: {module_id}: services must be a list")
                continue
            errors.extend(validate_module_settings(sensor_id, str(module_id), item.get("settings", {}), catalog_module))
            for service in services:
                if not isinstance(service, dict):
                    errors.append(f"{sensor_id}: {module_id}: service must be an object")
                    continue
                service_id = service.get("id")
                catalog_service = service_index.get(str(service_id))
                if not catalog_service:
                    errors.append(f"{sensor_id}: {module_id}: unknown service: {service_id}")
                    continue
                try:
                    host_port = int(service.get("host_port", catalog_service.get("default_host_port")))
                except (TypeError, ValueError):
                    errors.append(f"{sensor_id}: {module_id}/{service_id}: host_port must be an integer")
                    continue
                if not 1 <= host_port <= 65535:
                    errors.append(f"{sensor_id}: {module_id}/{service_id}: host_port out of range")
                    continue
                if item.get("enabled", True) is not False and service.get("enabled", True) is not False:
                    owner = used_ports.get(host_port)
                    if owner:
                        errors.append(f"{sensor_id}: port conflict tcp/{host_port}: {owner} and {module_id}/{service_id}")
                    used_ports[host_port] = f"{module_id}/{service_id}"
    return errors


def find_sensor(policy: dict[str, Any], sensor_id: str) -> dict[str, Any] | None:
    for sensor in policy.get("sensors", []):
        if sensor.get("id") == sensor_id:
            return sensor
    return None


def ensure_desired_module(sensor: dict[str, Any], catalog_module: dict[str, Any]) -> dict[str, Any]:
    desired = sensor.setdefault("desired_state", {})
    modules = desired.setdefault("modules", [])
    for module in modules:
        if module.get("id") == catalog_module.get("id"):
            return module
    module = {
        "id": catalog_module["id"],
        "enabled": False,
        "services": [
            {"id": service["id"], "enabled": True, "host_port": service.get("default_host_port", service.get("container_port"))}
            for service in catalog_module.get("services", [])
        ],
        "settings": {
            field["key"]: field.get("default", "")
            for field in catalog_module.get("config_schema", [])
            if isinstance(field, dict) and field.get("key")
        },
    }
    modules.append(module)
    return module


def ensure_desired_service(module: dict[str, Any], catalog_service: dict[str, Any]) -> dict[str, Any]:
    services = module.setdefault("services", [])
    for service in services:
        if service.get("id") == catalog_service.get("id"):
            return service
    service = {
        "id": catalog_service["id"],
        "enabled": True,
        "host_port": catalog_service.get("default_host_port", catalog_service.get("container_port")),
    }
    services.append(service)
    return service


def desired_state(policy: dict[str, Any], catalog: dict[str, Any], sensor_id: str) -> dict[str, Any] | None:
    sensor = find_sensor(policy, sensor_id)
    if not sensor:
        return None
    module_index = modules_by_id(catalog)
    desired = sensor.get("desired_state", {})
    planned_modules = []
    for item in desired.get("modules", []):
        module_id = item.get("id")
        catalog_module = module_index.get(module_id)
        if not catalog_module:
            continue
        service_index = services_by_id(catalog_module)
        planned_services = []
        for service in item.get("services", []):
            if service.get("enabled", True) is False:
                continue
            service_id = service.get("id")
            catalog_service = service_index.get(service_id)
            if not catalog_service:
                continue
            planned_services.append(
                {
                    **catalog_service,
                    "id": service_id,
                    "host_port": service.get("host_port", catalog_service.get("default_host_port")),
                }
            )
        planned_modules.append(
            {
                "id": module_id,
                "title": catalog_module.get("title"),
                "enabled": item.get("enabled", True) is not False,
                "status": catalog_module.get("status"),
                "runtime": catalog_module.get("runtime"),
                "resource_class": catalog_module.get("resource_class"),
                "settings": item.get("settings", {}),
                "services": planned_services,
            }
        )
    return {
        "sensor_id": sensor_id,
        "version": int(policy.get("version", 1)),
        "site": policy.get("site", {}),
        "host": sensor.get("host"),
        "architecture": sensor.get("architecture"),
        "profile": desired.get("profile"),
        "persona": desired.get("persona", {}),
        "modules": planned_modules,
    }
