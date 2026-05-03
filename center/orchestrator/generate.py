"""Generate ready-to-run sensor configuration directories."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from center.honeypots.catalog import HONEYPOT_CATALOG, SERVICE_CATALOG, default_honeypot, default_settings, legacy_honeypot

SENSORS_DIR = ROOT / "sensors"
INVENTORY_DIR = ROOT / "config"
PROJECT_FILE = INVENTORY_DIR / "project.json"
SAFE_SENSOR_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


FALLBACK_PROJECT = {
    "network": {
        "subnet": "192.168.10.0/24",
        "gateway": "192.168.10.1",
        "central_node": "192.168.10.2",
    },
    "sensors": [
        {
            "name": "sensor1",
            "host": "192.168.10.11",
            "role": "dmz",
            "profile": "opencanary",
            "services": ["ssh", "http", "ftp", "smtp"],
            "mask": {
                "hostname": "dmz-backup-gw",
                "os": "Debian GNU/Linux 13",
                "department": "DMZ",
                "asset_tag": "DMZ-BAK-01",
            },
        },
        {
            "name": "sensor2",
            "host": "192.168.10.12",
            "role": "office",
            "profile": "cowrie",
            "services": ["ssh", "telnet"],
            "mask": {
                "hostname": "office-filesrv-01",
                "os": "Debian GNU/Linux 13",
                "department": "Office",
                "asset_tag": "OFF-FS-01",
            },
        },
        {
            "name": "sensor3",
            "host": "192.168.10.13",
            "role": "ot-mining",
            "profile": "conpot",
            "services": ["http", "modbus"],
            "mask": {
                "hostname": "mine-telemetry-gw",
                "os": "Embedded Linux",
                "department": "Mining operations",
                "asset_tag": "OT-TEL-01",
            },
        },
    ],
}


def read_project() -> dict[str, Any]:
    """Load the rich project inventory or build a fallback from old files."""

    if PROJECT_FILE.exists():
        return json.loads(PROJECT_FILE.read_text(encoding="utf-8"))

    project = json.loads(json.dumps(FALLBACK_PROJECT))
    network_file = INVENTORY_DIR / "network.yml"
    if network_file.exists():
        text = network_file.read_text(encoding="utf-8")
        for key in ("subnet", "gateway", "central_node"):
            match = re.search(rf"{key}:\s*([0-9./]+)", text)
            if match:
                project["network"][key] = match.group(1)

    sensors_file = INVENTORY_DIR / "sensors.yml"
    if sensors_file.exists():
        hosts = read_sensor_hosts(sensors_file)
        for sensor in project["sensors"]:
            if sensor["name"] in hosts:
                sensor["host"] = hosts[sensor["name"]]
    return project


def read_sensor_hosts(path: Path) -> dict[str, str]:
    """Read simple Ansible-style sensor host addresses."""

    hosts: dict[str, str] = {}
    current: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        host_match = re.match(r"\s{4}([a-zA-Z0-9_-]+):\s*$", line)
        if host_match:
            current = host_match.group(1)
            continue
        address_match = re.match(r"\s+ansible_host:\s*([0-9.]+)\s*$", line)
        if current and address_match:
            hosts[current] = address_match.group(1)
    return hosts


def normalize_sensor(raw: dict[str, Any]) -> dict[str, Any]:
    """Fill missing sensor fields from the selected profile defaults."""

    profile = str(raw.get("profile", "opencanary"))
    profile = profile if profile in HONEYPOT_CATALOG else "opencanary"
    defaults = HONEYPOT_CATALOG[profile]
    mask = raw.get("mask") or {}
    name = str(raw.get("name", "sensor"))
    if not SAFE_SENSOR_NAME.fullmatch(name):
        raise ValueError(f"unsafe sensor name: {name!r}")
    raw_honeypots = raw.get("honeypots")
    if not isinstance(raw_honeypots, list) or not raw_honeypots:
        raw_honeypots = [legacy_honeypot(profile, raw.get("services"))]
    honeypots = [normalize_honeypot(item) for item in raw_honeypots]
    enabled_services = sorted({service for honeypot in honeypots for service in honeypot["services"]})
    return {
        "name": name,
        "host": str(raw.get("host", "192.168.10.10")),
        "role": str(raw.get("role", defaults["role"])),
        "profile": honeypots[0]["type"],
        "profile_description": HONEYPOT_CATALOG[honeypots[0]["type"]]["description"],
        "services": enabled_services,
        "honeypots": honeypots,
        "mask": {
            "hostname": str(mask.get("hostname", name)),
            "os": str(mask.get("os", "Debian GNU/Linux 13")),
            "department": str(mask.get("department", "Lab")),
            "asset_tag": str(mask.get("asset_tag", name.upper())),
            "notes": str(mask.get("notes", "")),
        },
    }


def normalize_honeypot(raw: Any) -> dict[str, Any]:
    """Normalize one honeypot selection from the project file."""

    if not isinstance(raw, dict):
        raw = default_honeypot("opencanary")
    honeypot_type = str(raw.get("type", "opencanary"))
    if honeypot_type not in HONEYPOT_CATALOG:
        honeypot_type = "opencanary"
    catalog = HONEYPOT_CATALOG[honeypot_type]
    allowed = set(catalog["services"])
    services = [str(item) for item in raw.get("services", catalog["default_services"]) if str(item) in allowed]
    if not services:
        services = list(catalog["default_services"])
    settings = default_settings(honeypot_type)
    if isinstance(raw.get("settings"), dict):
        for key, value in raw["settings"].items():
            if key in settings:
                settings[key] = value
    return {
        "type": honeypot_type,
        "enabled": bool(raw.get("enabled", True)),
        "services": services,
        "settings": settings,
    }


def build_services(sensor: dict[str, Any]) -> list[dict[str, Any]]:
    """Create service definitions consumed by fake-services."""

    services = []
    mask = sensor["mask"]
    for honeypot in sensor["honeypots"]:
        if not honeypot["enabled"]:
            continue
        honeypot_type = honeypot["type"]
        settings = honeypot["settings"]
        for service_name in honeypot["services"]:
            base = SERVICE_CATALOG.get(service_name)
            if not base:
                continue
            item = dict(base)
            item["name"] = f"{honeypot_type}:{service_name}"
            item["honeypot"] = honeypot_type
            item["service"] = service_name
            item["settings"] = settings
            item["banner"] = render_banner(item, mask, sensor)
            item["response"] = str(item.get("response", "")).format(**mask, sensor=sensor["name"])
            item["mask"] = mask
            services.append(item)
    return services


def render_banner(service: dict[str, Any], mask: dict[str, Any], sensor: dict[str, Any]) -> str:
    """Apply honeypot-specific banner settings to the generic service."""

    settings = service.get("settings", {})
    service_name = service.get("service")
    honeypot = service.get("honeypot")
    if honeypot == "cowrie" and service_name == "ssh":
        return str(settings.get("ssh_version") or service.get("banner", "")).format(**mask, sensor=sensor["name"])
    if honeypot == "heralding" and service_name == "ssh":
        return str(settings.get("ssh_version") or service.get("banner", "")).format(**mask, sensor=sensor["name"])
    if honeypot == "opencanary" and service_name == "http":
        skin = settings.get("http_skin", "basic")
        return (
            "HTTP/1.1 401 Unauthorized\r\n"
            f"Server: {skin}\r\n"
            "WWW-Authenticate: Basic realm=\"Restricted\"\r\n\r\n"
        )
    if honeypot == "conpot" and service_name == "http":
        vendor = settings.get("vendor", "Siemens")
        device = settings.get("device_name", "S7-200")
        return f"HTTP/1.1 200 OK\r\nServer: {vendor} {device}\r\nContent-Type: text/plain\r\n\r\n{device} online\r\n"
    base = str(service.get("banner", ""))
    return base.format(**mask, sensor=sensor["name"])


def render_env(sensor: dict[str, Any], central_node: str) -> str:
    """Render per-sensor environment variables."""

    ports = ",".join(str(service["port"]) for service in build_services(sensor))
    mask = sensor["mask"]
    return f"""SENSOR_NAME={sensor['name']}
SENSOR_HOST={sensor['host']}
SENSOR_ROLE={sensor['role']}
SENSOR_PROFILE={sensor['profile']}
MASK_HOSTNAME={mask['hostname']}
MASK_OS={mask['os']}
MASK_DEPARTMENT={mask['department']}
MASK_ASSET_TAG={mask['asset_tag']}
CENTRAL_NODE_HOST={central_node}
CENTRAL_URL=http://{central_node}:8080/api/events
CENTRAL_HEALTH_URL=http://{central_node}:8080/health
HONEYPOT_LOG_PATH=/logs/events.jsonl
FAKE_SERVICE_CONFIG=/config/services.json
FAKE_SERVICE_PORTS={ports}
DISPLAY_INTERVAL=10
"""


def render_ports(services: list[dict[str, Any]]) -> str:
    """Render compose port mappings."""

    lines = [f'      - "{service["port"]}:{service["port"]}"' for service in services]
    return "\n".join(lines) if lines else '      - "2222:2222"'


def render_compose(sensor: dict[str, Any]) -> str:
    """Render a compose file for one sensor."""

    services = build_services(sensor)
    return f"""services:
  fake-services:
    build:
      context: ../../sensor/containers/fake-services
    env_file:
      - .env
    ports:
{render_ports(services)}
    volumes:
      - ./logs:/logs
      - ./config:/config:ro
    restart: unless-stopped

  log-agent:
    build:
      context: ../../sensor/containers/log-agent
    env_file:
      - .env
    volumes:
      - ./logs:/logs
    depends_on:
      - fake-services
    restart: unless-stopped

  display-agent:
    build:
      context: ../../sensor/containers/display-agent
    env_file:
      - .env
    depends_on:
      - log-agent
    restart: unless-stopped
"""


def render_readme(sensor: dict[str, Any], central_node: str) -> str:
    """Render human-readable notes for one generated sensor."""

    services = build_services(sensor)
    service_rows = "\n".join(
        f"- `{item['name']}` on TCP `{item['port']}`: `{item.get('protocol', item['name'])}`"
        for item in services
    )
    mask = sensor["mask"]
    return f"""# {sensor['name']}

## Назначение

Сенсор `{sensor['name']}` предназначен для роли `{sensor['role']}` и использует профиль `{sensor['profile']}`.

Профиль: {sensor['profile_description']}.

## Сетевые параметры

- IP сенсора: `{sensor['host']}`
- Центральный узел: `{central_node}:8080`
- Отправка событий: `http://{central_node}:8080/api/events`

## Маскировка

- Имя-легенда: `{mask['hostname']}`
- ОС-легенда: `{mask['os']}`
- Подразделение: `{mask['department']}`
- Asset tag: `{mask['asset_tag']}`

## Сервисы-приманки

{service_rows}

## Компоненты

- `fake-services` - встроенный рабочий deception-слой с выбранными портами и баннерами.
- `log-agent` - читает локальный файл событий и отправляет их на центральный узел.
- `display-agent` - показывает статус сенсора и связь с центральным узлом.

## Запуск

```sh
docker compose up -d --build
docker compose ps
```

## Проверка

```sh
docker compose logs --tail=50
```
"""


def write_legacy_inventory(project: dict[str, Any]) -> None:
    """Keep old inventory files in sync for simple scripts and thesis notes."""

    network = project["network"]
    (INVENTORY_DIR / "network.yml").write_text(
        "network:\n"
        f"  subnet: {network['subnet']}\n"
        f"  gateway: {network['gateway']}\n"
        f"  central_node: {network['central_node']}\n",
        encoding="utf-8",
    )

    lines = ["all:", "  hosts:"]
    for raw in project["sensors"]:
        sensor = normalize_sensor(raw)
        lines.append(f"    {sensor['name']}:")
        lines.append(f"      ansible_host: {sensor['host']}")
    (INVENTORY_DIR / "sensors.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    project = read_project()
    central_node = str(project["network"]["central_node"])
    write_legacy_inventory(project)

    for raw_sensor in project["sensors"]:
        sensor = normalize_sensor(raw_sensor)
        sensor_dir = SENSORS_DIR / sensor["name"]
        config_dir = sensor_dir / "config"
        sensor_dir.mkdir(parents=True, exist_ok=True)
        config_dir.mkdir(parents=True, exist_ok=True)

        services = build_services(sensor)
        (sensor_dir / "README.md").write_text(render_readme(sensor, central_node), encoding="utf-8")
        (sensor_dir / ".env").write_text(render_env(sensor, central_node), encoding="utf-8")
        (sensor_dir / "docker-compose.yml").write_text(render_compose(sensor), encoding="utf-8")
        (config_dir / "services.json").write_text(
            json.dumps({"services": services}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
