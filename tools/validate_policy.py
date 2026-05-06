#!/usr/bin/env python3
"""Validate site policy against the honeypot module catalog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "catalog" / "honeypots.json"
DEFAULT_POLICY = ROOT / "config" / "site.example.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def catalog_index(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    modules = {}
    for module in catalog.get("modules", []):
        module_id = module.get("id")
        if not isinstance(module_id, str) or not module_id:
            raise ValueError("catalog module id must be a non-empty string")
        if module_id in modules:
            raise ValueError(f"duplicate catalog module: {module_id}")
        services = {}
        for service in module.get("services", []):
            service_id = service.get("id")
            if not isinstance(service_id, str) or not service_id:
                raise ValueError(f"{module_id}: service id must be a non-empty string")
            if service_id in services:
                raise ValueError(f"{module_id}: duplicate service: {service_id}")
            services[service_id] = service
        modules[module_id] = {**module, "services_by_id": services}
    return modules


def settings_schema_by_key(module: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {field["key"]: field for field in module.get("config_schema", []) if isinstance(field, dict) and field.get("key")}


def validate_settings(sensor_id: str, module_id: str, settings: Any, catalog_module: dict[str, Any]) -> list[str]:
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


def validate_policy(policy: dict[str, Any], modules: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    sensors = policy.get("sensors")
    if not isinstance(sensors, list) or not sensors:
        return ["policy must contain at least one sensor"]

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
        desired_modules = desired.get("modules")
        if not isinstance(desired_modules, list):
            errors.append(f"{sensor_id}: desired_state.modules must be a list")
            continue
        used_ports: dict[int, str] = {}
        for module in desired_modules:
            if not isinstance(module, dict):
                errors.append(f"{sensor_id}: module must be an object")
                continue
            module_id = module.get("id")
            if module_id not in modules:
                errors.append(f"{sensor_id}: unknown module: {module_id}")
                continue
            catalog_module = modules[module_id]
            services = module.get("services")
            if not isinstance(services, list):
                errors.append(f"{sensor_id}: {module_id}: services must be a list")
                continue
            errors.extend(validate_settings(sensor_id, str(module_id), module.get("settings", {}), catalog_module))
            for service in services:
                if not isinstance(service, dict):
                    errors.append(f"{sensor_id}: {module_id}: service must be an object")
                    continue
                service_id = service.get("id")
                if service_id not in catalog_module["services_by_id"]:
                    errors.append(f"{sensor_id}: {module_id}: unknown service: {service_id}")
                    continue
                try:
                    host_port = int(service.get("host_port", catalog_module["services_by_id"][service_id].get("default_host_port")))
                except (TypeError, ValueError):
                    errors.append(f"{sensor_id}: {module_id}/{service_id}: host_port must be an integer")
                    continue
                if not 1 <= host_port <= 65535:
                    errors.append(f"{sensor_id}: {module_id}/{service_id}: host_port out of range")
                    continue
                if module.get("enabled", True) is not False and service.get("enabled", True) is not False:
                    owner = used_ports.get(host_port)
                    if owner:
                        errors.append(f"{sensor_id}: port conflict tcp/{host_port}: {owner} and {module_id}/{service_id}")
                    used_ports[host_port] = f"{module_id}/{service_id}"
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate EDC site policy")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    modules = catalog_index(load_json(args.catalog))
    errors = validate_policy(load_json(args.policy), modules)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"ok: {args.policy} matches {args.catalog}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
