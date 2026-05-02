"""Interactive project configurator.

The UI is deliberately terminal-based and dependency-free so it works on a
fresh Armbian/Debian installation. Multi-select prompts behave like checkboxes:
enter comma-separated item numbers, for example "1,3,5".
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
PROJECT_FILE = ROOT / "inventory" / "project.json"


PROFILES = {
    "opencanary": {
        "title": "OpenCanary-like",
        "role": "dmz",
        "services": ["ssh", "http", "ftp", "smtp"],
        "description": "Мультисервисная приманка для DMZ и внутренних decoy-узлов.",
    },
    "cowrie": {
        "title": "Cowrie-like",
        "role": "office",
        "services": ["ssh", "telnet"],
        "description": "SSH/Telnet профиль для brute force и попыток входа.",
    },
    "heralding": {
        "title": "Heralding-like",
        "role": "office",
        "services": ["ssh", "telnet", "ftp", "smtp", "http"],
        "description": "Профиль для сбора попыток аутентификации.",
    },
    "conpot": {
        "title": "Conpot-like",
        "role": "ot-mining",
        "services": ["http", "modbus"],
        "description": "OT/ICS профиль для технологического сегмента.",
    },
    "dionaea": {
        "title": "Dionaea-like",
        "role": "dmz",
        "services": ["http", "ftp", "mysql"],
        "description": "Профиль для сетевых вредоносных подключений.",
    },
    "honeytrap": {
        "title": "Honeytrap-like",
        "role": "custom",
        "services": ["ssh", "http", "ftp", "printer"],
        "description": "Универсальный профиль для набора сервисов-приманок.",
    },
}


SERVICES = {
    "ssh": "SSH banner and login attempts",
    "telnet": "Telnet login prompt",
    "http": "HTTP service page",
    "ftp": "FTP banner and login failure",
    "smtp": "SMTP mail gateway banner",
    "mysql": "Database-like banner",
    "modbus": "OT/ICS Modbus touchpoint",
    "printer": "JetDirect-like printer port",
}


def ask(prompt: str, default: str) -> str:
    value = input(f"{prompt} [{default}]: ").strip()
    return value or default


def choose_one(title: str, options: list[str], default: str) -> str:
    print(f"\n{title}")
    for index, key in enumerate(options, start=1):
        profile = PROFILES.get(key)
        label = f"{key} - {profile['description']}" if profile else key
        print(f"  {index}. {label}")

    default_index = options.index(default) + 1 if default in options else 1
    raw = ask("Выбор", str(default_index))
    try:
        selected = options[int(raw) - 1]
    except (ValueError, IndexError):
        selected = default
    return selected


def choose_many(title: str, options: list[str], defaults: list[str]) -> list[str]:
    print(f"\n{title}")
    for index, key in enumerate(options, start=1):
        mark = "x" if key in defaults else " "
        print(f"  {index}. [{mark}] {key} - {SERVICES[key]}")

    default_numbers = ",".join(str(options.index(item) + 1) for item in defaults if item in options)
    raw = ask("Номера через запятую", default_numbers)
    selected: list[str] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            selected.append(options[int(part) - 1])
        except (ValueError, IndexError):
            continue
    return selected or defaults


def default_mask(name: str, profile: str) -> dict[str, str]:
    if profile == "conpot":
        return {
            "hostname": "mine-telemetry-gw",
            "os": "Embedded Linux",
            "department": "Mining operations",
            "asset_tag": "OT-TEL-01",
            "notes": "OT gateway decoy",
        }
    if profile == "cowrie":
        return {
            "hostname": "office-filesrv-01",
            "os": "Debian GNU/Linux 13",
            "department": "Office",
            "asset_tag": "OFF-FS-01",
            "notes": "internal SSH decoy",
        }
    return {
        "hostname": f"{name}-node",
        "os": "Debian GNU/Linux 13",
        "department": "IT",
        "asset_tag": name.upper(),
        "notes": "deception sensor",
    }


def configure_sensor(index: int, central_subnet_prefix: str) -> dict[str, Any]:
    name = ask(f"\nИмя сенсора {index}", f"sensor{index}")
    host = ask("IP сенсора", f"{central_subnet_prefix}.{10 + index}")
    profile = choose_one("Профиль honeypot/deception", list(PROFILES), "opencanary" if index == 1 else "cowrie")
    role = ask("Роль в сети", PROFILES[profile]["role"])
    services = choose_many("Сервисы-приманки", list(SERVICES), list(PROFILES[profile]["services"]))

    mask_default = default_mask(name, profile)
    print("\nМаскировка/легенда сенсора")
    mask = {
        "hostname": ask("Имя хоста-легенды", mask_default["hostname"]),
        "os": ask("ОС-легенда", mask_default["os"]),
        "department": ask("Подразделение", mask_default["department"]),
        "asset_tag": ask("Asset tag", mask_default["asset_tag"]),
        "notes": ask("Заметка", mask_default["notes"]),
    }

    return {
        "name": name,
        "host": host,
        "role": role,
        "profile": profile,
        "services": services,
        "mask": mask,
    }


def write_project(project: dict[str, Any]) -> None:
    PROJECT_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROJECT_FILE.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_generator() -> None:
    subprocess.run(["python3", str(ROOT / "orchestrator" / "generate.py")], cwd=ROOT, check=True)


def main() -> None:
    print("Early Detection Complex configurator")
    print("Выбирай профили и сервисы номерами. Enter оставляет значение по умолчанию.")

    subnet = ask("\nЛабораторная подсеть", "192.168.10.0/24")
    gateway = ask("Шлюз", "192.168.10.1")
    central_node = ask("IP центрального узла", "192.168.10.2")
    central_prefix = ".".join(central_node.split(".")[:3])
    sensor_count = int(ask("Количество сенсоров", "3"))

    sensors = [configure_sensor(index, central_prefix) for index in range(1, sensor_count + 1)]
    project = {
        "network": {
            "subnet": subnet,
            "gateway": gateway,
            "central_node": central_node,
        },
        "sensors": sensors,
    }

    write_project(project)
    run_generator()
    print(f"\nГотово: записан {PROJECT_FILE}")
    print(f"Конфигурации созданы в {ROOT / 'sensors'}")


if __name__ == "__main__":
    main()

