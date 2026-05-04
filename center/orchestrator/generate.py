"""Generate ready-to-run sensor configuration directories."""

from __future__ import annotations

import json
import re
import shutil
import sys
import textwrap
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from center.honeypots.catalog import HONEYPOT_CATALOG, SERVICE_CATALOG, default_honeypot, default_settings, legacy_honeypot, normalize_service

SENSORS_DIR = ROOT / "sensors"
CONFIG_DIR = ROOT / "config"
PROJECT_FILE = CONFIG_DIR / "project.json"
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
            "role": "office",
            "profile": "cowrie",
            "services": ["ssh", "telnet"],
            "mask": {
                "hostname": "office-filesrv-01",
                "os": "Debian GNU/Linux 13",
                "department": "Office",
                "asset_tag": "OFF-FS-01",
            },
        }
    ],
}


def read_project() -> dict[str, Any]:
    if PROJECT_FILE.exists():
        return json.loads(PROJECT_FILE.read_text(encoding="utf-8"))
    return json.loads(json.dumps(FALLBACK_PROJECT))


def normalize_sensor(raw: dict[str, Any]) -> dict[str, Any]:
    profile = str(raw.get("profile", "cowrie"))
    profile = profile if profile in HONEYPOT_CATALOG else "cowrie"
    defaults = HONEYPOT_CATALOG[profile]
    mask = raw.get("mask") or {}
    name = str(raw.get("name", "sensor"))
    if not SAFE_SENSOR_NAME.fullmatch(name):
        raise ValueError(f"unsafe sensor name: {name!r}")

    raw_honeypots = raw.get("honeypots")
    if not isinstance(raw_honeypots, list) or not raw_honeypots:
        raw_honeypots = [legacy_honeypot(profile, raw.get("services"))]
    honeypots = [normalize_honeypot(item) for item in raw_honeypots]
    enabled = [honeypot for honeypot in honeypots if honeypot["enabled"]]
    primary = enabled[0] if enabled else honeypots[0]

    return {
        "name": name,
        "host": str(raw.get("host", "192.168.10.10")),
        "role": str(raw.get("role", defaults["role"])),
        "profile": primary["type"],
        "profile_description": HONEYPOT_CATALOG[primary["type"]]["description"],
        "services": [service["name"] for honeypot in enabled for service in honeypot["services"] if service["enabled"]],
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
    if not isinstance(raw, dict):
        raw = default_honeypot("cowrie")
    honeypot_type = str(raw.get("type", "cowrie"))
    if honeypot_type not in HONEYPOT_CATALOG:
        honeypot_type = "cowrie"
    catalog = HONEYPOT_CATALOG[honeypot_type]
    raw_services = raw.get("services", catalog["default_services"])
    services = [normalize_service(item, honeypot_type) for item in raw_services]
    services = [service for service in services if service]
    if not services:
        services = [normalize_service(item, honeypot_type) for item in catalog["default_services"]]
        services = [service for service in services if service]
    settings = default_settings(honeypot_type)
    if isinstance(raw.get("settings"), dict):
        for key, value in raw["settings"].items():
            if key in settings:
                settings[key] = value
    return {
        "type": honeypot_type,
        "enabled": raw.get("enabled", True) is not False,
        "services": services,
        "settings": settings,
    }


def enabled_honeypots(sensor: dict[str, Any]) -> list[dict[str, Any]]:
    return [honeypot for honeypot in sensor["honeypots"] if honeypot["enabled"]]


def enabled_services(honeypot: dict[str, Any]) -> list[dict[str, Any]]:
    return [service for service in honeypot["services"] if service["enabled"]]


def render_env(sensor: dict[str, Any], central_node: str) -> str:
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
HONEYPOT_LOG_PATH=/cowrie/cowrie-git/var/log/cowrie/cowrie.json
DISPLAY_INTERVAL=10
"""


def render_port_lines(honeypot: dict[str, Any]) -> str:
    lines = []
    for service in enabled_services(honeypot):
        catalog = SERVICE_CATALOG[service["name"]]
        lines.append(f'      - "{service["host_port"]}:{catalog["container_port"]}"')
    return "\n".join(lines) if lines else '      - "2222:2222"'


def render_compose(sensor: dict[str, Any]) -> str:
    port_lines = []
    for honeypot in enabled_honeypots(sensor):
        if honeypot["type"] == "cowrie":
            port_lines.extend(render_port_lines(honeypot).splitlines())
    ports = "\n".join(port_lines) if port_lines else '      - "2222:2222"'
    return f"""services:
  edc-sensor:
    build:
      context: ../../sensor
    env_file:
      - .env
    ports:
{ports}
    volumes:
      - ./cowrie/etc:/cowrie/cowrie-git/etc:ro
      - ./cowrie/honeyfs:/cowrie/cowrie-git/src/cowrie/data/honeyfs:ro
      - ./logs:/cowrie/cowrie-git/var/log/cowrie
      - ./cowrie/downloads:/cowrie/cowrie-git/var/lib/cowrie/downloads
    restart: unless-stopped
"""


def render_cowrie_config(sensor: dict[str, Any], honeypot: dict[str, Any]) -> str:
    settings = honeypot["settings"]
    telnet_enabled = any(service["name"] == "telnet" and service["enabled"] for service in honeypot["services"])
    sftp_enabled = "true" if settings.get("sftp_enabled", True) else "false"
    return f"""[honeypot]
hostname = {settings.get('hostname') or sensor['mask']['hostname']}
etc_path = /cowrie/cowrie-git/etc
contents_path = /cowrie/cowrie-git/src/cowrie/data/honeyfs
log_path = var/log/cowrie
download_path = var/lib/cowrie/downloads
download_limit_size = {settings.get('download_limit_size', 10485760)}
auth_class = {settings.get('auth_class', 'UserDB')}
backend = {settings.get('backend', 'shell')}

[shell]
filesystem = /tmp/edc-cowrie/fs.pickle

[ssh]
enabled = true
version = {settings.get('ssh_version', 'SSH-2.0-OpenSSH_8.4')}
listen_endpoints = tcp:2222:interface=0.0.0.0
sftp_enabled = {sftp_enabled}

[telnet]
enabled = {str(telnet_enabled).lower()}
listen_endpoints = tcp:2223:interface=0.0.0.0

[output_jsonlog]
enabled = true
logfile = cowrie.json
"""


def render_cowrie_userdb(honeypot: dict[str, Any]) -> str:
    settings = honeypot["settings"]
    user = str(settings.get("login_user", "backup")).strip() or "backup"
    password = str(settings.get("login_password", "backup123"))
    return textwrap.dedent(
        f"""\
        # Format: username:x:password
        # x means login succeeds with the supplied password.
        {user}:x:{password}
        root:!:*
        admin:!:*
        """
    )


def setting_int(settings: dict[str, Any], key: str, fallback: int) -> int:
    try:
        return int(settings.get(key, fallback))
    except (TypeError, ValueError):
        return fallback


def render_passwd(sensor: dict[str, Any], honeypot: dict[str, Any]) -> str:
    settings = honeypot["settings"]
    user = str(settings.get("shell_user", settings.get("login_user", "backup"))).strip() or "backup"
    uid = setting_int(settings, "shell_uid", 1001)
    gid = setting_int(settings, "shell_gid", 1001)
    return textwrap.dedent(
        f"""\
        root:x:0:0:root:/root:/bin/bash
        daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
        www-data:x:33:33:www-data:/var/www:/usr/sbin/nologin
        {user}:x:{uid}:{gid}:{sensor['mask']['department']} service account:/home/{user}:/bin/bash
        """
    )


def render_group(honeypot: dict[str, Any]) -> str:
    settings = honeypot["settings"]
    user = str(settings.get("shell_user", settings.get("login_user", "backup"))).strip() or "backup"
    gid = setting_int(settings, "shell_gid", 1001)
    return textwrap.dedent(
        f"""\
        root:x:0:
        daemon:x:1:
        www-data:x:33:
        users:x:100:
        {user}:x:{gid}:{user}
        """
    )


def render_issue(sensor: dict[str, Any], honeypot: dict[str, Any]) -> str:
    settings = honeypot["settings"]
    return f"{sensor['mask']['os']} {settings.get('kernel_version', '5.10.0-23-amd64')} \\n \\l\n"


def render_motd(sensor: dict[str, Any]) -> str:
    return textwrap.dedent(
        f"""\
        Last login: Tue May  5 08:12:41 from 10.0.0.24

        {sensor['mask']['hostname']} maintenance window: Sunday 03:00-04:00.
        Unauthorized access is prohibited.
        """
    )


def render_bash_history() -> str:
    return textwrap.dedent(
        """\
        sudo systemctl status nginx
        tail -n 50 /var/log/auth.log
        df -h
        ls -la /srv/backups
        """
    )


def render_readme(sensor: dict[str, Any], central_node: str) -> str:
    rows = []
    for honeypot in enabled_honeypots(sensor):
        title = HONEYPOT_CATALOG[honeypot["type"]]["title"]
        for service in enabled_services(honeypot):
            container_port = SERVICE_CATALOG[service["name"]]["container_port"]
            rows.append(f"- `{title}` `{service['name']}`: host tcp/{service['host_port']} -> container tcp/{container_port}")
    services = "\n".join(rows) if rows else "- no enabled honeypot services"
    mask = sensor["mask"]
    return f"""# {sensor['name']}

## Назначение

Сенсор `{sensor['name']}` запускает единый контейнер `edc-sensor` с Cowrie и агентами внутри.

## Сетевые параметры

- IP сенсора: `{sensor['host']}`
- Центральный узел: `{central_node}:8080`
- Отправка событий: `http://{central_node}:8080/api/events`

## Маскировка

- Hostname: `{mask['hostname']}`
- OS: `{mask['os']}`
- Department: `{mask['department']}`
- Asset tag: `{mask['asset_tag']}`

## Honeypot Services

{services}

## Runtime

- `edc-sensor` - единый образ на базе `cowrie/cowrie:latest`, внутри Cowrie, log-agent и display-agent.
"""


def write_legacy_inventory(project: dict[str, Any]) -> None:
    network = project["network"]
    (CONFIG_DIR / "network.yml").write_text(
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
    (CONFIG_DIR / "sensors.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_sensor(sensor: dict[str, Any], central_node: str) -> None:
    sensor_dir = SENSORS_DIR / sensor["name"]
    if sensor_dir.exists():
        shutil.rmtree(sensor_dir)
    cowrie_etc = sensor_dir / "cowrie" / "etc"
    cowrie_honeyfs = sensor_dir / "cowrie" / "honeyfs"
    (sensor_dir / "logs").mkdir(parents=True, exist_ok=True)
    (sensor_dir / "cowrie" / "downloads").mkdir(parents=True, exist_ok=True)
    cowrie_etc.mkdir(parents=True, exist_ok=True)
    cowrie_honeyfs.mkdir(parents=True, exist_ok=True)

    (sensor_dir / ".env").write_text(render_env(sensor, central_node), encoding="utf-8")
    (sensor_dir / "docker-compose.yml").write_text(render_compose(sensor), encoding="utf-8")
    (sensor_dir / "README.md").write_text(render_readme(sensor, central_node), encoding="utf-8")
    for honeypot in enabled_honeypots(sensor):
        if honeypot["type"] == "cowrie":
            (cowrie_etc / "cowrie.cfg").write_text(render_cowrie_config(sensor, honeypot), encoding="utf-8")
            write_cowrie_persona(sensor, honeypot, cowrie_etc, cowrie_honeyfs)


def write_cowrie_persona(
    sensor: dict[str, Any],
    honeypot: dict[str, Any],
    cowrie_etc: Path,
    honeyfs: Path,
) -> None:
    settings = honeypot["settings"]
    user = str(settings.get("shell_user", settings.get("login_user", "backup"))).strip() or "backup"
    (cowrie_etc / "userdb.txt").write_text(render_cowrie_userdb(honeypot), encoding="utf-8")

    etc_dir = honeyfs / "etc"
    home_dir = honeyfs / "home" / user
    var_log_dir = honeyfs / "var" / "log"
    srv_backup_dir = honeyfs / "srv" / "backups"
    for path in (etc_dir, home_dir, var_log_dir, srv_backup_dir):
        path.mkdir(parents=True, exist_ok=True)

    (etc_dir / "hostname").write_text(sensor["mask"]["hostname"] + "\n", encoding="utf-8")
    (etc_dir / "issue.net").write_text(render_issue(sensor, honeypot), encoding="utf-8")
    (etc_dir / "motd").write_text(render_motd(sensor), encoding="utf-8")
    (etc_dir / "passwd").write_text(render_passwd(sensor, honeypot), encoding="utf-8")
    (etc_dir / "group").write_text(render_group(honeypot), encoding="utf-8")
    (home_dir / ".bash_history").write_text(render_bash_history(), encoding="utf-8")
    (home_dir / "README.txt").write_text(
        f"{sensor['mask']['hostname']} backup workspace\nAsset: {sensor['mask']['asset_tag']}\n",
        encoding="utf-8",
    )
    (srv_backup_dir / "inventory-notes.txt").write_text(
        f"asset={sensor['mask']['asset_tag']}\ndepartment={sensor['mask']['department']}\n",
        encoding="utf-8",
    )
    (var_log_dir / "auth.log").write_text(
        "May  5 08:12:41 sshd[1142]: Accepted password for backup from 10.0.0.24 port 52218 ssh2\n",
        encoding="utf-8",
    )


def main() -> None:
    project = read_project()
    central_node = str(project["network"]["central_node"])
    write_legacy_inventory(project)

    for raw_sensor in project["sensors"]:
        write_sensor(normalize_sensor(raw_sensor), central_node)


if __name__ == "__main__":
    main()
