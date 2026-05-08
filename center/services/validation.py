from typing import Any

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
    errors: list[str] = []
    if not isinstance(catalog, dict): return ["catalog must be an object"]
    if not isinstance(policy, dict): return ["policy must be an object"]

    module_index: dict[str, dict[str, Any]] = {}
    for module in catalog.get("modules", []):
        if not isinstance(module, dict): continue
        module_id = module.get("id")
        if not isinstance(module_id, str) or not module_id: continue
        if module_id in module_index:
            errors.append(f"duplicate catalog module: {module_id}")
        module_index[module_id] = module

    sensors = policy.get("sensors")
    if not isinstance(sensors, list) or not sensors:
        errors.append("policy must contain at least one sensor")
        return errors

    seen_sensors: set[str] = set()
    for sensor in sensors:
        if not isinstance(sensor, dict): continue
        sensor_id = sensor.get("id")
        if not isinstance(sensor_id, str) or not sensor_id: continue
        if sensor_id in seen_sensors:
            errors.append(f"duplicate sensor id: {sensor_id}")
        seen_sensors.add(sensor_id)

        desired = sensor.get("desired_state")
        if not isinstance(desired, dict): continue
        modules = desired.get("modules")
        if not isinstance(modules, list): continue

        used_ports: dict[int, str] = {}
        for item in modules:
            if not isinstance(item, dict): continue
            module_id = item.get("id")
            catalog_module = module_index.get(str(module_id))
            if not catalog_module: continue
            service_index = services_by_id(catalog_module)
            services = item.get("services")
            if not isinstance(services, list): continue
            
            errors.extend(validate_module_settings(sensor_id, str(module_id), item.get("settings", {}), catalog_module))
            
            for service in services:
                if not isinstance(service, dict): continue
                service_id = service.get("id")
                catalog_service = service_index.get(str(service_id))
                if not catalog_service: continue
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