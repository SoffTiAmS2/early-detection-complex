from __future__ import annotations

import json
import subprocess
from typing import Any


def container_rows(sensor_id: str) -> list[dict[str, Any]]:
    result = subprocess.run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label=edc.sensor_id={sensor_id}",
            "--format",
            "{{json .}}",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    rows: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        details = inspect_container(row.get("ID", ""))
        labels = details.get("labels", {})
        row["LabelModule"] = labels.get("edc.module")
        row.update(
            {
                "ContainerState": details.get("state"),
                "Running": details.get("running"),
                "RestartCount": details.get("restart_count"),
                "LastError": details.get("last_error"),
                "PortBindings": details.get("port_bindings", []),
            }
        )
        rows.append(row)
    return rows


def inspect_labels(container_id: str) -> dict[str, str]:
    return inspect_container(container_id).get("labels", {})


def inspect_container(container_id: str) -> dict[str, Any]:
    if not container_id:
        return {}
    result = subprocess.run(
        ["docker", "inspect", container_id],
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, list) or not payload:
        return {}
    item = payload[0] if isinstance(payload[0], dict) else {}
    state = item.get("State", {}) if isinstance(item.get("State"), dict) else {}
    config = item.get("Config", {}) if isinstance(item.get("Config"), dict) else {}
    return {
        "labels": config.get("Labels", {}) if isinstance(config.get("Labels"), dict) else {},
        "state": state.get("Status"),
        "running": state.get("Running"),
        "restart_count": item.get("RestartCount"),
        "last_error": state.get("Error") or None,
        "port_bindings": port_bindings(item),
    }


def port_bindings(inspect_payload: dict[str, Any]) -> list[dict[str, Any]]:
    network = inspect_payload.get("NetworkSettings", {})
    ports = network.get("Ports", {}) if isinstance(network, dict) else {}
    if not isinstance(ports, dict):
        return []
    bindings: list[dict[str, Any]] = []
    for container_port, host_bindings in ports.items():
        for binding in host_bindings or []:
            if not isinstance(binding, dict):
                continue
            bindings.append(
                {
                    "container_port": container_port,
                    "host_ip": binding.get("HostIp"),
                    "host_port": binding.get("HostPort"),
                }
            )
    return bindings
