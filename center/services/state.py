from typing import Any
from services.validation import modules_by_id, services_by_id, settings_schema_by_key

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
    if not sensor: return None
    
    module_index = modules_by_id(catalog)
    desired = sensor.get("desired_state", {})
    planned_modules = []
    
    for item in desired.get("modules", []):
        module_id = item.get("id")
        catalog_module = module_index.get(module_id)
        if not catalog_module: continue
        
        service_index = services_by_id(catalog_module)
        planned_services = []
        for service in item.get("services", []):
            if service.get("enabled", True) is False: continue
            service_id = service.get("id")
            catalog_service = service_index.get(service_id)
            if not catalog_service: continue
            planned_services.append({
                **catalog_service,
                "id": service_id,
                "host_port": service.get("host_port", catalog_service.get("default_host_port")),
            })
        
        planned_modules.append({
            "id": module_id,
            "title": catalog_module.get("title"),
            "enabled": item.get("enabled", True) is not False,
            "status": catalog_module.get("status"),
            "runtime": catalog_module.get("runtime"),
            "resource_class": catalog_module.get("resource_class"),
            "settings": item.get("settings", {}),
            "services": planned_services,
        })
        
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