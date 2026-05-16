from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from runtime_helpers import SUPPORTED_IMAGES, as_bool, selected_service_ids, selected_services


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
    image_root = Path(__file__).resolve().parent / "dockerfiles"
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
    enabled = selected_service_ids(module)
    services = selected_services(module)
    service_lines = [f"  {service.get('id')}: true" for service in services]
    lines = [
        f"sensor_name: {settings.get('sensor_name', sensor_id)}",
        f"log_path: {settings.get('log_path', '/logs/honeypy.log')}",
        f"http_title: {json.dumps(settings.get('http_title', 'Honeypot Web Panel'), ensure_ascii=False)}",
        f"template_id: {json.dumps(settings.get('template_id', 'generic-web'), ensure_ascii=False)}",
        "fake_paths:",
        *[f"  - {json.dumps(str(path), ensure_ascii=False)}" for path in settings.get("fake_paths", []) if str(path)],
        "login_prompts:",
        *[f"  - {json.dumps(str(item), ensure_ascii=False)}" for item in settings.get("login_prompts", []) if str(item)],
        f"banners: {json.dumps(settings.get('banners', {}), ensure_ascii=False)}",
        f"service_fingerprints: {json.dumps(settings.get('service_fingerprints', {}), ensure_ascii=False)}",
        "services:",
        *(service_lines or [f"  http: {'true' if 'http' in enabled else 'false'}"]),
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
    enabled_services = selected_services(module)
    cfg = {
        "sensor_id": sensor_id,
        "log_path": settings.get("log_path", "/logs/glutton.json"),
        "profile_id": settings.get("profile_id", desired.get("active_profile", desired.get("profile", ""))),
        "device_type": settings.get("device_type", desired.get("device_type", "")),
        "services": {str(service_id): service_id in enabled for service_id in sorted(enabled)},
        "listeners": [
            {
                "id": str(service.get("id")),
                "host_port": service.get("host_port"),
                "protocol": service.get("protocol", "tcp"),
                "description": service.get("description", ""),
            }
            for service in enabled_services
        ],
        "exposed_ports": settings.get("exposed_ports", desired.get("exposed_ports", [])),
        "banners": settings.get("banners", desired.get("banners", {})),
        "service_fingerprints": settings.get("service_fingerprints", desired.get("service_fingerprints", {})),
    }
    raw = str(settings.get("raw_glutton_yml") or "").strip()
    config_dir = runtime_dir / "glutton" / "config"
    if raw:
        (config_dir / "config.yaml").write_text(raw + "\n", encoding="utf-8")
        return
    source_dir = Path(__file__).resolve().parent / "dockerfiles" / "glutton"
    for name in ("config.yaml", "rules.yaml"):
        source = source_dir / name
        if source.exists():
            shutil.copy2(source, config_dir / name)
    (config_dir / "edc-profile.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
