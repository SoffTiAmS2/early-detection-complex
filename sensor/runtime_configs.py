from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from runtime_helpers import SUPPORTED_IMAGES, as_bool, selected_service_ids


def prepare_module_dirs(runtime_dir: Path, desired: dict[str, Any], sensor_id: str, errors: list[dict[str, Any]]) -> None:
    for module_id in SUPPORTED_IMAGES:
        base = runtime_dir / module_id
        for child in ("config", "data", "logs", "downloads", "tty", "image"):
            path = base / child
            path.mkdir(parents=True, exist_ok=True)
            path.chmod(0o777)
    prepare_image_contexts(runtime_dir, errors)
    write_cowrie_config(runtime_dir, desired, sensor_id)
    write_conpot_config(runtime_dir, desired, sensor_id)
    write_mailoney_config(runtime_dir, desired, sensor_id)
    write_honeypy_config(runtime_dir, desired, sensor_id)
    write_glutton_config(runtime_dir, desired, sensor_id)


def module_by_id(desired: dict[str, Any], module_id: str) -> dict[str, Any] | None:
    for module in desired.get("modules", []):
        if module.get("id") == module_id:
            return module
    return None


def prepare_image_contexts(runtime_dir: Path, errors: list[dict[str, Any]]) -> None:
    image_root = Path(__file__).resolve().parent / "images"
    for module_id in SUPPORTED_IMAGES:
        source = image_root / module_id
        target = runtime_dir / module_id / "image"
        dockerfile = source / "Dockerfile"
        if not dockerfile.exists():
            errors.append({"module": module_id, "stage": "image", "error": f"missing local Dockerfile: {dockerfile}"})
            continue
        for item in source.iterdir():
            destination = target / item.name
            if item.is_dir():
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.copytree(item, destination)
            else:
                shutil.copy2(item, destination)


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
        "[output_jsonlog]",
        "enabled = true",
        "logfile = /home/cowrie/cowrie/var/log/cowrie/cowrie.json",
        "epoch_timestamp = false",
        "",
    ]
    raw = str(settings.get("raw_cowrie_cfg") or "").strip()
    if raw:
        cowrie_cfg.extend(["", raw])
    (etc_dir / "cowrie.cfg").write_text("\n".join(cowrie_cfg) + "\n", encoding="utf-8")


def write_conpot_config(runtime_dir: Path, desired: dict[str, Any], sensor_id: str) -> None:
    module = module_by_id(desired, "conpot")
    if not module:
        return
    settings = module.get("settings", {})
    channels = settings.get("hpfriends.channels", "conpot.events")
    channel_items = [item.strip() for item in str(channels).replace("\n", ",").split(",") if item.strip()]
    lines = [
        "[common]",
        f"sensorid = {sensor_id}",
        "",
        "[virtual_file_system]",
        "data_fs_url = osfs:///data",
        "fs_url = tar:///usr/local/lib/python3.8/site-packages/conpot/data.tar",
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
        "[hpfriends]",
        f"enabled = {'True' if as_bool(settings.get('hpfriends.enabled'), False) else 'False'}",
        f"host = {settings.get('hpfriends.host', 'hpfriends.honeycloud.net')}",
        f"port = {int(settings.get('hpfriends.port', 20000))}",
        f"channels = {json.dumps(channel_items)}",
        "",
    ]
    raw = str(settings.get("raw_conpot_cfg") or "").strip()
    if raw:
        lines.extend(["# raw_conpot_cfg", raw])
    config_dir = runtime_dir / "conpot" / "config"
    (config_dir / "conpot.cfg").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_mailoney_config(runtime_dir: Path, desired: dict[str, Any], sensor_id: str) -> None:
    module = module_by_id(desired, "mailoney")
    if not module:
        return
    settings = module.get("settings", {})
    lines = [
        "[mailoney]",
        f"hostname = {settings.get('hostname', desired.get('persona', {}).get('hostname', sensor_id))}",
        f"banner = {settings.get('smtp_banner', '220 mail.example.local ESMTP')}",
        f"log_path = {settings.get('log_path', '/logs/mailoney.log')}",
    ]
    raw = str(settings.get("raw_mailoney_cfg") or "").strip()
    if raw:
        lines.extend(["", raw])
    config_dir = runtime_dir / "mailoney" / "config"
    (config_dir / "mailoney.cfg").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_honeypy_config(runtime_dir: Path, desired: dict[str, Any], sensor_id: str) -> None:
    module = module_by_id(desired, "honeypy")
    if not module:
        return
    settings = module.get("settings", {})
    lines = [
        f"sensor_name: {settings.get('sensor_name', sensor_id)}",
        f"log_path: {settings.get('log_path', '/logs/honeypy.log')}",
        "services:",
        f"  http: {'true' if 'http' in selected_service_ids(module) else 'false'}",
        f"  mysql: {'true' if 'mysql' in selected_service_ids(module) else 'false'}",
        f"  redis: {'true' if 'redis' in selected_service_ids(module) else 'false'}",
        f"  ftp: {'true' if 'ftp' in selected_service_ids(module) else 'false'}",
        f"  telnet: {'true' if 'telnet' in selected_service_ids(module) else 'false'}",
    ]
    raw = str(settings.get("raw_honeypy_yml") or "").strip()
    if raw:
        lines.extend(["", raw])
    config_dir = runtime_dir / "honeypy" / "config"
    (config_dir / "honeypy.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_glutton_config(runtime_dir: Path, desired: dict[str, Any], sensor_id: str) -> None:
    module = module_by_id(desired, "glutton")
    if not module:
        return
    settings = module.get("settings", {})
    enabled = selected_service_ids(module)
    cfg = {
        "sensor_id": sensor_id,
        "log_path": settings.get("log_path", "/logs/glutton.json"),
        "services": {
            "docker_api": "docker_api" in enabled,
            "mqtt": "mqtt" in enabled,
            "k8s_api": "k8s_api" in enabled,
            "rdp": "rdp" in enabled,
            "vnc": "vnc" in enabled,
            "sip": "sip" in enabled,
        },
    }
    raw = str(settings.get("raw_glutton_yml") or "").strip()
    config_dir = runtime_dir / "glutton" / "config"
    if raw:
        (config_dir / "glutton.yml").write_text(raw + "\n", encoding="utf-8")
        return
    (config_dir / "glutton.yml").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
