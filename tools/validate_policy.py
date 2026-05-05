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


def validate_policy(policy: dict[str, Any], modules: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    sensors = policy.get("sensors")
    if not isinstance(sensors, list) or not sensors:
        return ["policy must contain at least one sensor"]

    for sensor in sensors:
        sensor_id = sensor.get("id")
        if not isinstance(sensor_id, str) or not sensor_id:
            errors.append("sensor id must be a non-empty string")
            continue
        desired = sensor.get("desired_state")
        if not isinstance(desired, dict):
            errors.append(f"{sensor_id}: desired_state must be an object")
            continue
        used_ports: dict[int, str] = {}
        for module in desired.get("modules", []):
            module_id = module.get("id")
            if module_id not in modules:
                errors.append(f"{sensor_id}: unknown module: {module_id}")
                continue
            catalog_module = modules[module_id]
            for service in module.get("services", []):
                service_id = service.get("id")
                if service_id not in catalog_module["services_by_id"]:
                    errors.append(f"{sensor_id}: {module_id}: unknown service: {service_id}")
                    continue
                try:
                    host_port = int(service.get("host_port"))
                except (TypeError, ValueError):
                    errors.append(f"{sensor_id}: {module_id}/{service_id}: host_port must be an integer")
                    continue
                if not 1 <= host_port <= 65535:
                    errors.append(f"{sensor_id}: {module_id}/{service_id}: host_port out of range")
                    continue
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
