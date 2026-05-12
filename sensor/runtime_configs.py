from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from runtime_helpers import HERALDING_CAPABILITIES, SUPPORTED_IMAGES, as_bool, selected_service_ids, selected_services, yaml_scalar


def prepare_module_dirs(runtime_dir: Path, desired: dict[str, Any], sensor_id: str, errors: list[dict[str, Any]]) -> None:
    for module_id in SUPPORTED_IMAGES:
        base = runtime_dir / module_id
        for child in ("config", "data", "logs", "downloads", "tty", "image"):
            path = base / child
            path.mkdir(parents=True, exist_ok=True)
            path.chmod(0o777)
    prepare_cowrie_image(runtime_dir, errors)
    write_cowrie_config(runtime_dir, desired, sensor_id)
    write_opencanary_config(runtime_dir, desired, sensor_id, errors)
    write_heralding_config(runtime_dir, desired)
    write_conpot_config(runtime_dir, desired, sensor_id)


def module_by_id(desired: dict[str, Any], module_id: str) -> dict[str, Any] | None:
    for module in desired.get("modules", []):
        if module.get("id") == module_id:
            return module
    return None


def prepare_cowrie_image(runtime_dir: Path, errors: list[dict[str, Any]]) -> None:
    source = Path(__file__).resolve().parent / "images" / "cowrie"
    target = runtime_dir / "cowrie" / "image"
    dockerfile = source / "Dockerfile"
    if not dockerfile.exists():
        errors.append({"module": "cowrie", "stage": "image", "error": f"missing local Dockerfile: {dockerfile}"})
        return
    shutil.copy2(dockerfile, target / "Dockerfile")


def write_cowrie_config(runtime_dir: Path, desired: dict[str, Any], sensor_id: str) -> None:
    module = module_by_id(desired, "cowrie")
    if not module:
        return
    settings = module.get("settings", {})
    etc_dir = runtime_dir / "cowrie" / "config"
    userdb = str(settings.get("userdb_entries") or "root:x:!root\nadmin:x:admin")
    (etc_dir / "userdb.txt").write_text(userdb.rstrip() + "\n", encoding="utf-8")
    hostname = settings.get("hostname") or desired.get("persona", {}).get("hostname") or sensor_id
    cowrie_cfg = [
        "[honeypot]",
        f"hostname = {hostname}",
        f"logtype = {settings.get('logtype', 'rotating')}",
        f"download_limit_size = {int(settings.get('download_limit_size', 10485760))}",
        f"authentication_timeout = {int(settings.get('authentication_timeout', 120))}",
        f"idle_timeout = {int(settings.get('idle_timeout', 180))}",
        "",
        "[ssh]",
        f"enabled = {'yes' if 'ssh' in selected_service_ids(module) else 'no'}",
        "listen_endpoints = tcp:2222:interface=0.0.0.0",
        f"version = {settings.get('ssh_version', 'SSH-2.0-OpenSSH_8.4')}",
        "",
        "[telnet]",
        f"enabled = {'yes' if 'telnet' in selected_service_ids(module) else 'no'}",
        "listen_endpoints = tcp:2223:interface=0.0.0.0",
        "",
        "[output_json]",
        "enabled = true",
        "",
        "[output_prometheus]",
        "enabled = true",
        "port = 9000",
        "",
    ]
    raw = str(settings.get("raw_cowrie_cfg") or "").strip()
    if raw:
        cowrie_cfg.extend(["", raw])
    (etc_dir / "cowrie.cfg").write_text("\n".join(cowrie_cfg) + "\n", encoding="utf-8")


def write_opencanary_config(runtime_dir: Path, desired: dict[str, Any], sensor_id: str, errors: list[dict[str, Any]]) -> None:
    module = module_by_id(desired, "opencanary")
    if not module:
        return
    settings = module.get("settings", {})
    enabled = {str(service.get("id")) for service in selected_services(module)}
    config = {
        "device.node_id": settings.get("device.node_id", f"opencanary-{sensor_id}"),
        "ip.ignorelist": [item.strip() for item in str(settings.get("ip.ignorelist", "")).replace("\n", ",").split(",") if item.strip()],
        "logger": {
            "class": "PyLogger",
            "kwargs": {
                "formatters": {"plain": {"format": "%(message)s"}},
                "handlers": {"console": {"class": "logging.StreamHandler", "stream": "ext://sys.stdout"}},
            },
        },
    }
    for service_id in ("ftp", "http", "redis", "mysql", "mssql", "ssh", "telnet", "smb"):
        config[f"{service_id}.enabled"] = service_id in enabled
    config.update(
        {
            "ftp.banner": settings.get("ftp.banner", "FTP server ready"),
            "http.banner": settings.get("http.banner", "nginx/1.18.0"),
            "http.skin": settings.get("http.skin", "nasLogin"),
            "mysql.banner": settings.get("mysql.banner", "5.5.43-0ubuntu0.14.04.1"),
            "ssh.version": settings.get("ssh.version", "SSH-2.0-OpenSSH_5.1p1 Debian-4"),
            "telnet.banner": settings.get("telnet.banner", ""),
        }
    )
    raw = str(settings.get("raw_opencanary_conf") or "").strip()
    if raw:
        try:
            overlay = json.loads(raw)
            if isinstance(overlay, dict):
                config.update(overlay)
        except json.JSONDecodeError as exc:
            errors.append({"module": "opencanary", "stage": "config", "error": str(exc)})
    config_dir = runtime_dir / "opencanary" / "config"
    (config_dir / "opencanary.conf").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_heralding_config(runtime_dir: Path, desired: dict[str, Any]) -> None:
    module = module_by_id(desired, "heralding")
    if not module:
        return
    settings = module.get("settings", {})
    enabled = selected_service_ids(module)
    lines = [
        "public_ip_as_destination_ip: false",
        f"bind_host: {yaml_scalar(settings.get('listen_addr', '0.0.0.0'))}",
        "activity_logging:",
        "  file:",
        "    enabled: true",
        f"    session_csv_log_file: {yaml_scalar('/logs/' + str(settings.get('session_csv_logfile', 'log_session.csv')))}",
        f"    session_json_log_file: {yaml_scalar('/logs/' + str(settings.get('session_json_logfile', 'log_session.json')))}",
        f"    authentication_log_file: {yaml_scalar('/logs/' + str(settings.get('auth_logfile', 'log_auth.csv')))}",
        "  syslog:",
        "    enabled: false",
        "  hpfeeds:",
        "    enabled: false",
        "  curiosum:",
        "    enabled: false",
        "hash_cracker:",
        "  enabled: true",
        "  wordlist_file: '/usr/lib/python3.12/site-packages/heralding/wordlist.txt'",
        "capabilities:",
    ]
    for capability, port in HERALDING_CAPABILITIES.items():
        lines.extend([f"  {capability}:", f"    enabled: {'true' if capability in enabled else 'false'}", f"    port: {port}", "    timeout: 30"])
        if capability in {"ftp", "pop3", "smtp", "http", "ssh"}:
            lines.append("    protocol_specific_data:")
            lines.extend(heralding_protocol_data(capability))
    raw = str(settings.get("raw_heralding_yml") or "").strip()
    if raw:
        lines.extend(["", "# raw_heralding_yml", raw])
    config_dir = runtime_dir / "heralding" / "config"
    (config_dir / "heralding.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def heralding_protocol_data(capability: str) -> list[str]:
    if capability == "ftp":
        return ["      max_attempts: 3", "      banner: \"Microsoft FTP Server\"", "      syst_type: \"Windows-NT\""]
    if capability == "pop3":
        return ["      max_attempts: 3", "      banner: \"+OK POP3 server ready\""]
    if capability == "smtp":
        return ["      banner: \"Microsoft ESMTP MAIL service ready\"", "      fqdn: \"\""]
    if capability == "http":
        return ["      banner: \"\""]
    if capability == "ssh":
        return ["      banner: \"SSH-2.0-OpenSSH_6.6.1p1 Ubuntu-2ubuntu2.8\""]
    return []


def write_conpot_config(runtime_dir: Path, desired: dict[str, Any], sensor_id: str) -> None:
    module = module_by_id(desired, "conpot")
    if not module:
        return
    settings = module.get("settings", {})
    channels = settings.get("hpfriends.channels", "conpot.events")
    channel_items = [item.strip() for item in channels.replace("\n", ",").split(",") if item.strip()] if isinstance(channels, str) else [str(item) for item in channels]
    lines = [
        "[common]",
        f"sensorid = {sensor_id}",
        "",
        "[virtual_file_system]",
        "data_fs_url = osfs:///data",
        "fs_url = tar:///home/conpot/.local/lib/python3.6/site-packages/conpot-0.6.0-py3.6.egg/conpot/data.tar",
        "",
        "[session]",
        "timeout = 30",
        "",
        "[json]",
        "enabled = True",
        "filename = /logs/conpot.json",
        "",
        "[sqlite]",
        f"enabled = {'True' if as_bool(settings.get('sqlite.enabled'), False) else 'False'}",
        "filename = /data/conpot.sqlite",
        "",
        "[mysql]",
        "enabled = False",
        "",
        "[syslog]",
        "enabled = False",
        "",
        "[hpfriends]",
        f"enabled = {'True' if as_bool(settings.get('hpfriends.enabled'), False) else 'False'}",
        f"host = {settings.get('hpfriends.host', 'hpfriends.honeycloud.net')}",
        f"port = {int(settings.get('hpfriends.port', 20000))}",
        f"channels = {json.dumps(channel_items)}",
        "",
        "[taxii]",
        "enabled = False",
        "",
        "[fetch_public_ip]",
        f"enabled = {'True' if as_bool(settings.get('fetch_public_ip.enabled'), False) else 'False'}",
        f"urls = {json.dumps([settings.get('fetch_public_ip.url', 'http://whatismyip.akamai.com/')])}",
        "",
        "[change_mac_addr]",
        "enabled = False",
    ]
    raw = str(settings.get("raw_conpot_cfg") or "").strip()
    if raw:
        lines.extend(["", raw])
    config_dir = runtime_dir / "conpot" / "config"
    (config_dir / "conpot.cfg").write_text("\n".join(lines) + "\n", encoding="utf-8")
