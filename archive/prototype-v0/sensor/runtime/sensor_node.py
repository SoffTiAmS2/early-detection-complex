"""Managed sensor node status and early network activity agent."""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


TCP_STATES = {
    "01": "established",
    "02": "syn_sent",
    "03": "syn_recv",
    "04": "fin_wait1",
    "05": "fin_wait2",
    "06": "time_wait",
    "07": "close",
    "08": "close_wait",
    "09": "last_ack",
    "0A": "listen",
    "0B": "closing",
}


def now_ts() -> float:
    return time.time()


def load_json_env(name: str, fallback: Any) -> Any:
    raw = os.getenv(name)
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def post_json(url: str, payload: dict[str, Any], timeout: int = 5) -> bool:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"sensor-node: central send failed: {exc}", flush=True)
        return False


def base_event(event_type: str) -> dict[str, Any]:
    return {
        "type": event_type,
        "timestamp": now_ts(),
        "sensor": os.getenv("SENSOR_NAME", "sensor-unknown"),
        "sensor_host": os.getenv("SENSOR_HOST", ""),
        "role": os.getenv("SENSOR_ROLE", "unknown"),
        "profile": os.getenv("SENSOR_PROFILE", "cowrie"),
        "sensor_version": os.getenv("SENSOR_VERSION", "0.1.0"),
        "mask_hostname": os.getenv("MASK_HOSTNAME", ""),
        "mask_department": os.getenv("MASK_DEPARTMENT", ""),
        "source": "sensor-node",
    }


def parse_ipv4(value: str) -> str:
    raw = bytes.fromhex(value)
    return socket.inet_ntoa(raw[::-1])


def parse_ipv6(value: str) -> str:
    raw = bytes.fromhex(value)
    words = [raw[index : index + 4][::-1] for index in range(0, len(raw), 4)]
    return socket.inet_ntop(socket.AF_INET6, b"".join(words))


def parse_address(value: str, ipv6: bool) -> tuple[str, int]:
    address, port_hex = value.split(":", 1)
    host = parse_ipv6(address) if ipv6 else parse_ipv4(address)
    return host, int(port_hex, 16)


def read_tcp_table(path: Path, ipv6: bool) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        fields = line.split()
        if len(fields) < 4:
            continue
        local_host, local_port = parse_address(fields[1], ipv6)
        remote_host, remote_port = parse_address(fields[2], ipv6)
        state = TCP_STATES.get(fields[3], fields[3])
        rows.append(
            {
                "local_host": local_host,
                "local_port": local_port,
                "remote_host": remote_host,
                "remote_port": remote_port,
                "state": state,
            }
        )
    return rows


def read_tcp_connections() -> list[dict[str, Any]]:
    return read_tcp_table(Path("/proc/net/tcp"), ipv6=False) + read_tcp_table(Path("/proc/net/tcp6"), ipv6=True)


def load_port_map() -> dict[int, dict[str, Any]]:
    port_map: dict[int, dict[str, Any]] = {}
    configured_ports = load_json_env("HONEYPOT_PORTS", [])
    if not configured_ports:
        config_path = Path(os.getenv("CONFIG_PATH", "/opt/edc/config/sensor_node.json"))
        if config_path.exists():
            try:
                configured_ports = json.loads(config_path.read_text(encoding="utf-8")).get("ports", [])
            except (json.JSONDecodeError, OSError):
                configured_ports = []
    for item in configured_ports:
        try:
            container_port = int(item["container_port"])
        except (KeyError, TypeError, ValueError):
            continue
        port_map[container_port] = {
            "honeypot": item.get("honeypot", "unknown"),
            "service": item.get("service", "unknown"),
            "container_port": container_port,
            "host_port": item.get("host_port", container_port),
        }
    return port_map


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def status_payload(port_map: dict[int, dict[str, Any]]) -> dict[str, Any]:
    event = base_event("sensor.status")
    event.update(
        {
            "status": "online",
            "honeypots": sorted({item["honeypot"] for item in port_map.values()}),
            "services": sorted({item["service"] for item in port_map.values()}),
            "ports": list(port_map.values()),
            "components": {
                "cowrie": "managed",
                "log_agent": "managed",
                "display_agent": "managed",
                "sensor_node": "managed",
            },
        }
    )
    return event


def connection_event(connection: dict[str, Any], service: dict[str, Any]) -> dict[str, Any]:
    event = base_event("sensor.connection_seen")
    event.update(
        {
            "severity": "medium",
            "honeypot": service["honeypot"],
            "service": service["service"],
            "dst_port": service["host_port"],
            "container_port": service["container_port"],
            "src_ip": connection["remote_host"],
            "src_port": connection["remote_port"],
            "connection_state": connection["state"],
            "reason": "connection to managed honeypot port",
        }
    )
    return event


def main() -> None:
    central_url = os.getenv("CENTRAL_URL", "http://central-node:8080/api/events")
    state_path = Path(os.getenv("STATUS_PATH", "/opt/edc/state/sensor_status.json"))
    status_interval = float(os.getenv("SENSOR_STATUS_INTERVAL", "30"))
    watch_interval = float(os.getenv("NETWATCH_INTERVAL", "2"))
    port_map = load_port_map()
    seen_connections: set[tuple[str, int, int, str]] = set()
    last_status = 0.0

    print(f"sensor-node: started ports={list(port_map)} central={central_url}", flush=True)
    while True:
        now = now_ts()
        if now - last_status >= status_interval:
            status = status_payload(port_map)
            write_state(state_path, status)
            post_json(central_url, status)
            last_status = now

        for connection in read_tcp_connections():
            service = port_map.get(int(connection["local_port"]))
            if not service or connection["state"] == "listen":
                continue
            fingerprint = (
                str(connection["remote_host"]),
                int(connection["remote_port"]),
                int(connection["local_port"]),
                str(connection["state"]),
            )
            if fingerprint in seen_connections:
                continue
            seen_connections.add(fingerprint)
            post_json(central_url, connection_event(connection, service))

        time.sleep(watch_interval)


if __name__ == "__main__":
    main()
