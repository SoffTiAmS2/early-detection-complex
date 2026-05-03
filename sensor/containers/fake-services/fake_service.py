"""Small configurable TCP honeypot used as a safe default profile.

It accepts TCP connections, sends a service-specific banner, records the peer
address and closes the connection. This is not a replacement for Cowrie,
OpenCanary or Conpot; it gives the stand a working deception layer before
external honeypots are added.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import threading
import time
from pathlib import Path
from typing import Any


STOP = threading.Event()


def now_ts() -> float:
    return time.time()


def parse_ports(raw: str) -> list[dict[str, Any]]:
    ports: list[dict[str, Any]] = []
    for item in raw.split(","):
        item = item.strip()
        if item:
            ports.append(
                {
                    "name": f"tcp-{item}",
                    "port": int(item),
                    "protocol": "tcp",
                    "banner": os.getenv("FAKE_SERVICE_BANNER", "SSH-2.0-OpenSSH_8.4\r\n"),
                    "response": "",
                }
            )
    return ports


def load_services() -> list[dict[str, Any]]:
    config_path = Path(os.getenv("FAKE_SERVICE_CONFIG", "/config/services.json"))
    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        services = data.get("services", [])
        if isinstance(services, list):
            return [service for service in services if isinstance(service, dict) and "port" in service]
    return parse_ports(os.getenv("FAKE_SERVICE_PORTS", "2222,8081"))


def append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def handle_client(conn: socket.socket, addr: tuple[str, int], service: dict[str, Any], log_path: Path) -> None:
    source_ip, source_port = addr
    event = {
        "timestamp": now_ts(),
        "type": "connection",
        "service": service.get("name", "fake-tcp"),
        "protocol": service.get("protocol", "tcp"),
        "listen_port": service["port"],
        "source_ip": source_ip,
        "source_port": source_port,
        "mask": service.get("mask", {}),
    }
    append_event(log_path, event)

    banner = str(service.get("banner", "")).encode("utf-8")
    response = str(service.get("response", "")).encode("utf-8")
    try:
        if banner:
            conn.sendall(banner)
        conn.settimeout(2)
        try:
            data = conn.recv(1024)
        except socket.timeout:
            data = b""
        if data:
            event["payload_preview"] = data[:80].decode("utf-8", errors="replace")
            append_event(log_path, event | {"type": "payload"})
            if response:
                conn.sendall(response)
    finally:
        conn.close()


def serve_service(service: dict[str, Any], log_path: Path) -> None:
    port = int(service["port"])
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", port))
        server.listen(50)
        server.settimeout(1)
        print(f"fake-service: listening on {service.get('name', 'tcp')} tcp/{port}")

        while not STOP.is_set():
            try:
                conn, addr = server.accept()
            except socket.timeout:
                continue
            thread = threading.Thread(target=handle_client, args=(conn, addr, service, log_path), daemon=True)
            thread.start()


def main() -> None:
    log_path = Path(os.getenv("HONEYPOT_LOG_PATH", "/logs/events.jsonl"))
    services = load_services()
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    signal.signal(signal.SIGINT, lambda *_: STOP.set())

    threads = [threading.Thread(target=serve_service, args=(service, log_path), daemon=True) for service in services]
    for thread in threads:
        thread.start()

    while not STOP.is_set():
        time.sleep(1)


if __name__ == "__main__":
    main()
